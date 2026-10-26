"""Asks the model to reread the fields named by failed checks (F6 AC3, AC8)."""

import uuid
from typing import Any

from app.core.logging import get_logger
from app.extractions.exact_json import dumps_exact
from app.llm.gateway import Gateway
from app.llm.types import (
    CallContext,
    FilePart,
    LlmError,
    LlmRequest,
    LlmResult,
    Prompt,
    TextPart,
)
from app.schemas_registry import bundle
from app.validation.agent import Fix, get_path
from app.validation.checks import Issue

log = get_logger(__name__)

FIXES_SCHEMA_ID = "docflow/agent-fixes/v1"


def describe(doc_type: str, issues: list[Issue], data: dict[str, Any]) -> str:
    """The request text: what failed, and the current value of every field involved."""
    lines = [f"Document type: {doc_type}", "", "Failed checks:"]
    lines += [f"- {issue.message} (fields: {', '.join(issue.paths)})" for issue in issues]
    lines += ["", "Current values:"]
    for path in sorted({path for issue in issues for path in issue.paths}):
        try:
            value = get_path(data, path)
        except (KeyError, IndexError, TypeError, ValueError):
            value = None
        lines.append(f"- {path}: {dumps_exact(value)}")
    return "\n".join(lines)


class GatewayRereader:
    """A rereader for one document. The agent's work is best-effort: when the model can't be
    reached, it proposes nothing and the issues go to a person (spec edge cases)."""

    def __init__(
        self,
        gateway: Gateway,
        prompt: Prompt,
        *,
        file: FilePart,
        context: CallContext,
    ) -> None:
        self._gateway = gateway
        self._prompt = prompt
        self._file = file
        self._context = context
        self.call_ids: list[uuid.UUID] = []

    async def reread(
        self, *, doc_type: str, issues: list[Issue], data: dict[str, Any]
    ) -> list[Fix]:
        request = LlmRequest(
            task="validate",
            prompt=self._prompt,
            parts=[TextPart(describe(doc_type, issues, data)), self._file],
            response_schema=bundle(FIXES_SCHEMA_ID),
            context=self._context,
        )
        try:
            result = await self._generate(request)
        except LlmError as exc:
            log.warning("agent_reread_failed", error_type=type(exc).__name__)
            return []
        self.call_ids.append(result.call_id)
        return [
            Fix(
                path=fix["path"],
                value=fix["value"],
                confidence=float(fix["confidence"]),
                reason=fix["reason"],
            )
            for fix in result.data["fixes"]
        ]

    async def _generate(self, request: LlmRequest) -> LlmResult:
        return await self._gateway.generate(request, validate_with=FIXES_SCHEMA_ID)
