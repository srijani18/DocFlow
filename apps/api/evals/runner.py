"""Runs the dataset through classification and extraction, once per model (F11 plan §2).

Extraction uses the *true* document type, so extraction accuracy isn't mixed up with
classification mistakes; classification is scored on its own. No cache and no database:
calls are recorded in memory (F11 AC6, AC8).

With `agent=True`, a second pass runs the validation agent on every extraction (F6 AC10).
Duplicates are looked up among the other documents of the run.
"""

import asyncio
import json
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from app.extractions import envelope
from app.llm.circuit import CircuitBreaker
from app.llm.gateway import Credentials, Gateway
from app.llm.prompts import load_prompt
from app.llm.providers.base import Provider
from app.llm.recording import CallRecord, MemoryCallRecorder
from app.llm.routing import RouteEntry
from app.llm.types import (
    CallContext,
    FilePart,
    InvalidOutputError,
    LlmError,
    LlmRequest,
    LlmResult,
    TextPart,
    TransientLlmError,
)
from app.schemas_registry import bundle
from app.validation.agent import run_agent
from app.validation.approval import can_auto_approve, corrected_confidence
from app.validation.checks import NUMBER_FIELDS, WorkspaceLookups, party_of
from app.validation.rereader import FIXES_SCHEMA_ID, GatewayRereader
from evals.scoring import FieldResult, score

EVAL_WORKSPACE = uuid.UUID(int=0)  # a placeholder: evals belong to no workspace
CLASSIFY_SCHEMA = "docflow/classification/v1"


@dataclass(frozen=True)
class Document:
    id: str
    path: Path
    content_type: str
    doc_type: str
    schema_id: str
    source: str
    truth: dict[str, Any]
    unlabelled: list[str]
    expected_issues: list[str] = field(default_factory=list)


@dataclass
class AgentOutcome:
    """The validation agent's pass over one extraction (F6 AC10)."""

    fields: list[FieldResult]
    issues: list[str]  # error and warning check names left after the agent
    fixes: int
    auto_approved: bool


@dataclass
class DocumentOutcome:
    id: str
    source: str
    doc_type: str
    predicted_type: str | None = None
    fields: list[FieldResult] = field(default_factory=list)
    error: str | None = None
    invalid: bool = False
    calls: list[CallRecord] = field(default_factory=list)
    predicted: dict[str, Any] | None = None
    confidence: dict[str, Any] = field(default_factory=dict)
    expected_issues: list[str] = field(default_factory=list)
    agent: AgentOutcome | None = None

    @property
    def classified_correctly(self) -> bool:
        return self.predicted_type == self.doc_type


@dataclass
class ModelRun:
    route: str
    outcomes: list[DocumentOutcome] = field(default_factory=list)
    agent_calls: list[CallRecord] = field(default_factory=list)


class StaticKeys:
    """The operator's own keys from the environment (F11 D0)."""

    def __init__(self, keys: Mapping[str, str]) -> None:
        self._keys = dict(keys)

    async def keys_for(self, workspace_id: uuid.UUID) -> Mapping[str, str]:
        return self._keys

    async def mark_rejected(self, workspace_id: uuid.UUID, provider: str) -> None:
        self._keys.pop(provider, None)


def load_manifest(path: Path) -> tuple[int, list[Document]]:
    raw = json.loads(path.read_text())
    documents = [
        Document(
            id=entry["id"],
            path=path.parent / entry["file"],
            content_type=entry["content_type"],
            doc_type=entry["doc_type"],
            schema_id=entry["schema_id"],
            source=entry["source"],
            truth=entry["truth"],
            unlabelled=entry.get("unlabelled", []),
            expected_issues=entry.get("expected_issues", []),
        )
        for entry in raw["documents"]
    ]
    return int(raw["version"]), documents


def select(documents: Sequence[Document], limit: int | None) -> list[Document]:
    """A stable sample that rotates through (source, type) groups, so a small limit still
    covers synthetic and CORD documents of every type."""
    groups: dict[tuple[str, str], list[Document]] = {}
    for document in sorted(documents, key=lambda d: d.id):
        groups.setdefault((document.source, document.doc_type), []).append(document)
    ordered: list[Document] = []
    queues = [groups[key] for key in sorted(groups)]
    while any(queues):
        for queue in queues:
            if queue:
                ordered.append(queue.pop(0))
    return ordered[:limit] if limit else ordered


Sleep = Callable[[float], Any]


async def _call(
    gateway: Gateway, request: LlmRequest, validate_with: Any, *, retries: int, sleep: Sleep
) -> dict[str, Any]:
    for attempt in range(retries + 1):
        try:
            return (await gateway.generate(request, validate_with=validate_with)).data
        except TransientLlmError as exc:
            if attempt == retries:
                raise
            # A provider's retry-after if it gave one, else 15 s, 30 s, 60 s, 120 s: long
            # enough to ride out a brief network or provider outage mid-run.
            await sleep(exc.retry_after_seconds or 15 * 2**attempt)
    raise AssertionError("unreachable")


class RetryingRereader(GatewayRereader):
    """The agent's rereader with the eval's patience for transient errors."""

    def __init__(self, *args: Any, retries: int, sleep: Sleep, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._retries = retries
        self._sleep = sleep

    async def _generate(self, request: LlmRequest) -> LlmResult:
        request = replace(request, use_cache=False)
        for attempt in range(self._retries + 1):
            try:
                return await self._gateway.generate(request, validate_with=FIXES_SCHEMA_ID)
            except TransientLlmError as exc:
                if attempt == self._retries:
                    raise
                await self._sleep(exc.retry_after_seconds or 15 * 2**attempt)
        raise AssertionError("unreachable")


def dataset_lookups(
    outcomes: Sequence[DocumentOutcome], current: DocumentOutcome
) -> WorkspaceLookups:
    """Duplicates among the run's other extractions; every vendor counts as known."""

    async def find_duplicates(gstin: str | None, name: str | None, number: str) -> list[str]:
        found = []
        for other in outcomes:
            if other is current or other.predicted is None or other.doc_type != current.doc_type:
                continue
            party = party_of(other.doc_type, other.predicted)
            same_vendor = (gstin and party.get("gstin") == gstin) or (
                name and str(party.get("name") or "").casefold() == name.casefold()
            )
            if same_vendor and other.predicted.get(NUMBER_FIELDS[other.doc_type]) == number:
                found.append(other.id)
        return found

    async def vendor_seen(_gstin: str | None, _name: str | None) -> bool:
        return True

    return WorkspaceLookups(find_duplicates=find_duplicates, vendor_seen=vendor_seen)


async def run_agent_pass(
    run: ModelRun,
    documents: Sequence[Document],
    gateway: Gateway,
    *,
    today: date,
    pace_seconds: float,
    retries: int,
    sleep: Sleep,
) -> None:
    by_id = {document.id: document for document in documents}
    prompt = load_prompt("validate/v1")
    for outcome in run.outcomes:
        document = by_id[outcome.id]
        if outcome.predicted is None:
            continue
        rereader = RetryingRereader(
            gateway,
            prompt,
            file=FilePart(document.content_type, document.path.read_bytes()),
            context=CallContext(
                workspace_id=EVAL_WORKSPACE, document_id=None, job_id=None, attempt=1
            ),
            retries=retries,
            sleep=sleep,
        )
        result = await run_agent(
            document.doc_type,
            document.schema_id,
            outcome.predicted,
            today=today,
            rereader=rereader,
            lookups=dataset_lookups(run.outcomes, outcome),
        )
        confidence = (
            corrected_confidence(outcome.confidence, result)
            if result.changed
            else outcome.confidence
        )
        outcome.agent = AgentOutcome(
            fields=score(
                bundle(document.schema_id),
                document.truth,
                result.data,
                unlabelled=document.unlabelled,
            ),
            issues=sorted({i.check for i in result.issues if i.severity != "info"}),
            fixes=len(result.fixes),
            auto_approved=can_auto_approve(result, confidence),
        )
        if result.rounds:
            await sleep(pace_seconds)


async def run_model(
    route: RouteEntry,
    documents: Sequence[Document],
    *,
    providers: Mapping[str, Provider],
    credentials: Credentials,
    pace_seconds: float = 0,
    retries: int = 4,
    sleep: Sleep = asyncio.sleep,
    agent: bool = False,
    today: date | None = None,
) -> ModelRun:
    recorder = MemoryCallRecorder()
    gateway = Gateway(
        sessionmaker=None,
        providers=providers,
        routes={"classify": (route,), "extract": (route,), "validate": (route,)},
        credentials=credentials,
        # Evals measure every document; never skip a provider mid-run.
        breaker=CircuitBreaker(threshold=10_000),
        recorder=recorder,
    )
    classify_prompt, extract_prompt = load_prompt("classify/v1"), load_prompt("extract/v1")
    run = ModelRun(route=str(route))
    for document in documents:
        outcome = DocumentOutcome(
            id=document.id,
            source=document.source,
            doc_type=document.doc_type,
            expected_issues=document.expected_issues,
        )
        before = len(recorder.calls)
        file = FilePart(document.content_type, document.path.read_bytes())
        context = CallContext(workspace_id=EVAL_WORKSPACE, document_id=None, job_id=None, attempt=1)
        try:
            classified = await _call(
                gateway,
                LlmRequest(
                    "classify",
                    classify_prompt,
                    [file],
                    bundle(CLASSIFY_SCHEMA),
                    context,
                    use_cache=False,
                ),
                CLASSIFY_SCHEMA,
                retries=retries,
                sleep=sleep,
            )
            outcome.predicted_type = str(classified["doc_type"])
            await sleep(pace_seconds)
            schema_id = document.schema_id

            def check(answer: dict[str, Any], schema_id: str = schema_id) -> list[str]:
                return envelope.validate(schema_id, answer)

            extracted = await _call(
                gateway,
                LlmRequest(
                    "extract",
                    extract_prompt,
                    [TextPart(f"Document type: {document.doc_type}"), file],
                    envelope.response_schema(schema_id),
                    context,
                    use_cache=False,
                ),
                check,
                retries=retries,
                sleep=sleep,
            )
            predicted = extracted["data"]
            outcome.predicted = predicted
            outcome.confidence = dict(envelope.confidence_map(extracted))
        except InvalidOutputError as exc:
            outcome.invalid, outcome.error, predicted = True, str(exc), None
        except LlmError as exc:
            outcome.error, predicted = f"{type(exc).__name__}: {exc}", None
        fields = score(
            bundle(document.schema_id), document.truth, predicted, unlabelled=document.unlabelled
        )
        if predicted is None:
            # No answer at all: even fields whose truth is null weren't "extracted" (null
            # would otherwise match the missing answer and inflate accuracy).
            fields = [replace(result, correct=False) for result in fields]
        outcome.fields = fields
        outcome.calls = recorder.calls[before:]
        run.outcomes.append(outcome)
        await sleep(pace_seconds)
    if agent:
        # "Today" for the date checks: the latest calendar date anywhere (UTC+14).
        latest = (datetime.now(UTC) + timedelta(hours=14)).date()
        await run_agent_pass(
            run,
            documents,
            gateway,
            today=today or latest,
            pace_seconds=pace_seconds,
            retries=retries,
            sleep=sleep,
        )
        # The rereads come after every extraction call, so they're the recorder's tail.
        run.agent_calls = recorder.calls[sum(len(o.calls) for o in run.outcomes) :]
    return run
