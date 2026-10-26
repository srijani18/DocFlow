import json
import re
from typing import Any

import pytest

from app.llm.providers.fake import FakeProvider
from app.llm.routing import RouteEntry
from app.llm.types import LlmError, ProviderRequest, TextPart, TransientLlmError
from evals import report
from evals.__main__ import main
from evals.paths import MANIFEST
from evals.runner import StaticKeys, load_manifest, run_model, select

ROUTE = RouteEntry("fake", "fake-model")


def perfect(documents_by_type: dict[str, dict[str, Any]]) -> Any:
    """A provider that classifies correctly and returns the truth (and one wrong field)."""

    def script(request: ProviderRequest) -> dict[str, Any] | LlmError:
        if "classify" in request.instructions.lower()[:40]:
            return {"doc_type": "invoice", "confidence": 0.9}
        doc_type = request.parts[0].text.removeprefix("Document type: ")  # type: ignore[union-attr]
        data = json.loads(json.dumps(documents_by_type[doc_type]))
        if doc_type == "receipt":
            data["total"] = None  # one deliberate mistake
        return {"data": data, "confidence": []}

    return script


@pytest.fixture
def sample() -> list[Any]:
    _, documents = load_manifest(MANIFEST)
    picked = [d for d in select(documents, None) if d.source == "synthetic"]
    return [next(d for d in picked if d.doc_type == t) for t in ("invoice", "receipt")]


async def no_sleep(_seconds: float) -> None:
    return None


async def test_full_run_with_fake_provider(sample: list[Any]) -> None:
    truths = {d.doc_type: d.truth for d in sample}
    provider = FakeProvider(perfect(truths))

    run = await run_model(
        ROUTE,
        sample,
        providers={"fake": provider},
        credentials=StaticKeys({"fake": "k"}),
        sleep=no_sleep,
    )
    summary = report.summarise(run)

    assert summary.documents == 2
    assert summary.classification_accuracy == 0.5  # the receipt was classified as an invoice
    assert 0.9 < summary.field_accuracy < 1.0
    assert summary.by_doc_type["invoice"] == 1.0
    assert summary.all_correct_rate == 0.5
    assert summary.by_field["total.amount"] == 0.5
    assert summary.served_models == ["fake-model"]
    assert summary.cost_per_document_usd is not None
    # no cache: every document made its own two calls
    assert len(provider.requests) == 4
    assert isinstance(provider.requests[1].parts[0], TextPart)


async def test_provider_errors_count_as_wrong_and_the_run_continues(sample: list[Any]) -> None:
    calls = 0

    def flaky(_request: ProviderRequest) -> Any:
        nonlocal calls
        calls += 1
        return TransientLlmError("503", retry_after_seconds=1)

    run = await run_model(
        ROUTE,
        sample,
        providers={"fake": FakeProvider(flaky)},
        credentials=StaticKeys({"fake": "k"}),
        retries=1,
        sleep=no_sleep,
    )
    summary = report.summarise(run)

    assert summary.error_rate == 1.0
    assert summary.field_accuracy == 0.0
    assert calls == 4  # 2 documents, each 1 try + 1 retry


async def test_ac4_comparison_table_and_report_files(sample: list[Any]) -> None:
    truths = {d.doc_type: d.truth for d in sample}
    runs = [
        await run_model(
            ROUTE,
            sample,
            providers={"fake": FakeProvider(perfect(truths))},
            credentials=StaticKeys({"fake": "k"}),
            sleep=no_sleep,
        ),
        await run_model(
            RouteEntry("fake", "other-model"),
            sample,
            providers={"fake": FakeProvider(perfect(truths))},
            credentials=StaticKeys({"fake": "k"}),
            sleep=no_sleep,
        ),
    ]
    meta = {
        "run_id": "20261026-1200-abc1234-beef",
        "commit": "abc1234",
        "created_at": "2026-10-26T12:00:00+00:00",
        "dataset_version": 1,
        "documents": 2,
        "prompt_versions": ["classify/v1", "extract/v1"],
        "models": ["fake:fake-model", "fake:other-model"],
    }

    markdown = report.to_markdown(meta, runs)
    record = report.to_json(meta, runs)

    assert "| `fake:fake-model` |" in markdown
    assert "| `fake:other-model` |" in markdown
    assert "## Field accuracy by document type" in markdown
    assert "## Per field (worst first)" in markdown
    assert record["commit"] == "abc1234"
    assert record["prompt_versions"] == ["classify/v1", "extract/v1"]
    assert len(record["summaries"]) == 2
    assert {d["id"] for d in record["documents"]["fake:fake-model"]} == {d.id for d in sample}


async def test_ac7_skips_cleanly_without_keys(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for variable in ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.setenv(variable, "")
    monkeypatch.setattr("evals.__main__.REPO_ROOT", MANIFEST.parent)  # no .env there

    code = await main(["--models", "groq:llama"])

    assert code == 0
    assert "Skipping evals: no provider keys configured" in capsys.readouterr().out


def test_ac5_run_id_format() -> None:
    assert re.fullmatch(r"\d{8}-\d{4}-[0-9a-z]+-[0-9a-f]{4}", "20261026-1200-abc1234-beef")
