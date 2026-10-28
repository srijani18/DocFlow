"""F13 metrics, from seeded rows with known answers.

The clock is frozen at 2026-01-10 12:00 UTC, so the 7-day period starts at
2026-01-04 00:00 UTC.
"""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.models import Document, DocumentEvent, Upload
from app.extractions.models import Extraction
from app.jobs.models import Job
from app.llm.models import LlmCall
from app.review.models import Correction
from tests.support.clock import FrozenClock
from tests.support.documents import as_user
from tests.support.identity import TwoWorkspaces

NOW = datetime(2026, 1, 10, 12, tzinfo=UTC)
RECENT = NOW - timedelta(days=1)
OLD = NOW - timedelta(days=20)


@pytest.fixture(autouse=True)
def frozen_now(clock: FrozenClock) -> None:
    clock.advance(seconds=(NOW - clock.now()).total_seconds())


class Seed:
    """Rows for workspace A (or B), written straight to the tables the metrics read."""

    def __init__(self, session: AsyncSession, w: TwoWorkspaces, workspace: str = "a") -> None:
        self.session = session
        self.workspace_id = w.a.id if workspace == "a" else w.b.id
        self.user_id = w.a_admin.id if workspace == "a" else w.b_admin.id

    async def document(self, *, created_at: datetime = RECENT, **values: Any) -> uuid.UUID:
        sha = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
        upload = Upload(
            workspace_id=self.workspace_id,
            created_by_user_id=self.user_id,
            filename="scan.pdf",
            content_type="application/pdf",
            size_bytes=10,
            sha256=sha,
            expires_at=created_at,
        )
        self.session.add(upload)
        await self.session.flush()
        document = Document(
            workspace_id=self.workspace_id,
            upload_id=upload.id,
            storage_path=f"x/{sha}",
            filename="scan.pdf",
            content_type="application/pdf",
            size_bytes=10,
            sha256=sha,
            created_by_user_id=self.user_id,
            created_at=created_at,
            **{"status": "NEEDS_REVIEW", "status_changed_at": created_at} | values,
        )
        self.session.add(document)
        await self.session.flush()
        return document.id

    async def approved(
        self, *, by_person: bool, data: dict[str, Any], at: datetime = RECENT
    ) -> uuid.UUID:
        document_id = await self.document(
            status="APPROVED",
            approved_at=at,
            approved_by_agent=not by_person,
            approved_by_user_id=self.user_id if by_person else None,
        )
        extraction = Extraction(
            workspace_id=self.workspace_id,
            document_id=document_id,
            version=1,
            source="human" if by_person else "model",
            schema_id="docflow/invoice/v1",
            data=data,
            processing_generation=1,
        )
        self.session.add(extraction)
        await self.session.flush()
        document = await self.session.get_one(Document, document_id)
        document.approved_extraction_id = extraction.id
        await self.session.flush()
        return document_id

    async def correction(self, document_id: uuid.UUID, path: str) -> None:
        document = await self.session.get_one(Document, document_id)
        self.session.add(
            Correction(
                workspace_id=self.workspace_id,
                document_id=document_id,
                extraction_id=document.approved_extraction_id,
                path=path,
                old_value=1,
                new_value=2,
                user_id=self.user_id,
            )
        )
        await self.session.flush()

    async def events(self, document_id: uuid.UUID, *steps: tuple[str, float]) -> None:
        """Status changes at seconds after RECENT, in order."""
        for status, seconds in steps:
            self.session.add(
                DocumentEvent(
                    workspace_id=self.workspace_id,
                    document_id=document_id,
                    to_status=status,
                    created_at=RECENT + timedelta(seconds=seconds),
                )
            )
            await self.session.flush()

    async def call(
        self,
        *,
        task: str = "extract",
        outcome: str = "ok",
        document_id: uuid.UUID | None = None,
        cost: str | None = None,
        provider: str = "gemini",
        model: str = "gemini-2.5-flash",
        fallback: bool = False,
        latency_ms: int = 1000,
        created_at: datetime = RECENT,
    ) -> None:
        self.session.add(
            LlmCall(
                workspace_id=self.workspace_id,
                document_id=document_id,
                task=task,
                provider=provider,
                model=model,
                prompt_version=f"{task}/v1",
                attempt=1,
                outcome=outcome,
                cost_usd=Decimal(cost) if cost is not None else None,
                latency_ms=latency_ms,
                fallback=fallback,
                created_at=created_at,
            )
        )
        await self.session.flush()

    async def job(self, status: str, *, created_at: datetime = RECENT) -> None:
        document_id = await self.document()
        self.session.add(
            Job(
                workspace_id=self.workspace_id,
                document_id=document_id,
                kind="process_document",
                status=status,
                idempotency_key=f"process_document:{document_id}:1",
                created_at=created_at,
            )
        )
        await self.session.flush()


async def metrics(
    client: httpx.AsyncClient, w: TwoWorkspaces, period: str = "7d", workspace: str = "a"
) -> dict[str, Any]:
    ws, user = (w.a, w.a_reviewer) if workspace == "a" else (w.b, w.b_admin)
    response = await client.get(
        f"/v1/workspaces/{ws.id}/metrics", params={"period": period}, headers=as_user(user)
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_ac1_approvals_and_field_accuracy(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces, db_session: AsyncSession
) -> None:
    seed = Seed(db_session, two_workspaces)
    await seed.approved(by_person=False, data={"a": 1})  # nobody checked it: no fields
    edited = await seed.approved(by_person=True, data={"a": 1, "b": None, "c": {"d": "x"}})
    await seed.correction(edited, "a")
    await seed.correction(edited, "a")  # saved twice: still one field
    await seed.approved(by_person=True, data={"items": [{"q": 1}, {"q": 2}]})
    await seed.approved(by_person=True, data={"a": 1}, at=OLD)  # before the period
    await seed.document(status="NEEDS_REVIEW")

    week = (await metrics(db_client, two_workspaces))["headline"]
    ever = (await metrics(db_client, two_workspaces, "all"))["headline"]

    assert week["approved"] == 3
    assert week["approved_without_edits"] == 2
    assert week["approved_by_agent"] == 1
    assert week["approved_without_edits_rate"] == pytest.approx(2 / 3)
    assert (week["fields_reviewed"], week["fields_unchanged"]) == (5, 4)
    assert week["field_accuracy"] == pytest.approx(0.8)
    assert (ever["approved"], ever["fields_reviewed"]) == (4, 6)


async def test_ac1_cost_per_document(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces, db_session: AsyncSession
) -> None:
    seed = Seed(db_session, two_workspaces)
    first, second = await seed.document(), await seed.document()
    await seed.call(document_id=first, cost="0.010000")
    await seed.call(document_id=first, task="classify", cost="0.002000")
    await seed.call(document_id=second, outcome="cache_hit", cost="0")
    await seed.call(task="embed", cost="5")  # a search query: no document
    await seed.call(document_id=second, cost="1", created_at=OLD)

    week = (await metrics(db_client, two_workspaces))["headline"]

    assert week["documents_processed"] == 2
    assert week["cost_usd"] == pytest.approx(0.012)
    assert week["cost_per_document_usd"] == pytest.approx(0.006)


async def test_ac1_processing_time_of_latest_finished_run(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces, db_session: AsyncSession
) -> None:
    seed = Seed(db_session, two_workspaces)
    quick, retried, running = [await seed.document() for _ in range(3)]
    await seed.events(quick, ("UPLOADED", 0), ("CLASSIFYING", 1), ("NEEDS_REVIEW", 10))
    await seed.events(
        retried,
        ("UPLOADED", 0),
        ("FAILED", 5),
        ("UPLOADED", 100),  # the retry starts a new run
        ("NEEDS_REVIEW", 130),
        ("APPROVED", 900),  # a person approving later isn't processing
    )
    await seed.events(running, ("UPLOADED", 0), ("EXTRACTING", 3))

    week = (await metrics(db_client, two_workspaces))["headline"]

    assert week["processing_runs"] == 2
    assert week["processing_seconds_p50"] == pytest.approx(20)
    assert week["processing_seconds_p95"] == pytest.approx(29)


async def test_ac2_volume_per_day_and_by_status(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces, db_session: AsyncSession
) -> None:
    seed = Seed(db_session, two_workspaces)
    await seed.document(doc_type="invoice", status="APPROVED")
    await seed.document(doc_type="receipt")
    await seed.document(created_at=NOW - timedelta(days=3), status="FAILED")
    await seed.document(created_at=OLD, doc_type="invoice")

    volume = (await metrics(db_client, two_workspaces))["volume"]

    assert [day["date"] for day in volume["per_day"]] == [
        f"2026-01-{day:02}" for day in range(4, 11)
    ]
    assert [day["uploaded"] for day in volume["per_day"]] == [0, 0, 0, 1, 0, 2, 0]
    assert volume["by_status"] == {
        "UPLOADED": 0,
        "CLASSIFYING": 0,
        "EXTRACTING": 0,
        "VALIDATING": 0,
        "NEEDS_REVIEW": 1,
        "APPROVED": 1,
        "FAILED": 1,
    }
    assert volume["by_doc_type"] == {
        "invoice": 1,
        "receipt": 1,
        "purchase_order": 0,
        "other": 0,
        "unclassified": 1,
    }


async def test_ac3_ai_provider_reliability(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces, db_session: AsyncSession
) -> None:
    seed = Seed(db_session, two_workspaces)
    await seed.call(outcome="error", latency_ms=30_000)
    await seed.call(outcome="ok", latency_ms=1000)
    await seed.call(outcome="ok", latency_ms=3000)
    await seed.call(outcome="ok", provider="groq", model="llama", fallback=True, latency_ms=500)
    await seed.call(outcome="cache_hit", latency_ms=1)
    await seed.call(outcome="invalid_output", created_at=OLD)

    llm = (await metrics(db_client, two_workspaces))["llm"]

    assert [task["task"] for task in llm] == ["classify", "extract", "validate", "embed"]
    extract = llm[1]
    assert extract["calls"] == 5
    assert extract["outcomes"] == {
        "ok": 3,
        "error": 1,
        "invalid_output": 0,
        "cache_hit": 1,
        "skipped": 0,
    }
    assert extract["fallback_rate"] == pytest.approx(1 / 4)
    assert extract["served_by"] == [
        {"provider": "gemini", "model": "gemini-2.5-flash", "calls": 3},
        {"provider": "groq", "model": "llama", "calls": 1},
    ]
    assert extract["latency_ms_p50"] == pytest.approx(1000)
    assert llm[0] == {
        "task": "classify",
        "calls": 0,
        "outcomes": {"ok": 0, "error": 0, "invalid_output": 0, "cache_hit": 0, "skipped": 0},
        "fallback_rate": None,
        "served_by": [],
        "latency_ms_p50": None,
    }


async def test_ac4_queue_and_failures(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces, db_session: AsyncSession
) -> None:
    seed = Seed(db_session, two_workspaces)
    await seed.job("queued", created_at=NOW - timedelta(minutes=5))
    await seed.job("queued", created_at=NOW - timedelta(minutes=1))
    await seed.job("running")
    await seed.job("dead")
    await seed.job("succeeded")
    for reason in ["No AI key", "No AI key", "Unreadable file", None]:
        await seed.document(status="FAILED", failure_reason=reason)
    await seed.document(status="FAILED", failure_reason="Old", status_changed_at=OLD)

    queue = (await metrics(db_client, two_workspaces))["queue"]

    assert (queue["queued"], queue["running"], queue["dead"]) == (2, 1, 1)
    assert queue["oldest_queued_seconds"] == pytest.approx(300)
    assert queue["failed"] == 4
    assert queue["failure_reasons"] == [
        {"reason": "No AI key", "documents": 2},
        {"reason": "Unreadable file", "documents": 1},
        {"reason": "Unknown", "documents": 1},
    ]


async def test_ac5_metrics_are_per_workspace(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces, db_session: AsyncSession
) -> None:
    w = two_workspaces
    seed = Seed(db_session, w)
    document = await seed.approved(by_person=True, data={"a": 1})
    await seed.call(document_id=document, cost="0.5")
    await seed.job("queued")

    other = await metrics(db_client, w, workspace="b")
    outsider = await db_client.get(f"/v1/workspaces/{w.a.id}/metrics", headers=as_user(w.b_admin))

    assert outsider.status_code == 404
    assert other["headline"]["approved"] == 0
    assert other["headline"]["cost_usd"] is None
    assert other["queue"]["queued"] == 0
    assert other["llm"][1]["calls"] == 0


async def test_empty_workspace_has_no_figures(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces
) -> None:
    body = await metrics(db_client, two_workspaces, "all")

    assert body["since"] is None
    assert body["volume"]["per_day"] == []
    assert {key: value for key, value in body["headline"].items() if value not in (0, None)} == {}
    assert body["queue"]["oldest_queued_seconds"] is None


async def test_period_must_be_known(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces
) -> None:
    w = two_workspaces
    response = await db_client.get(
        f"/v1/workspaces/{w.a.id}/metrics", params={"period": "90d"}, headers=as_user(w.a_admin)
    )
    default = await db_client.get(f"/v1/workspaces/{w.a.id}/metrics", headers=as_user(w.a_admin))

    assert response.status_code == 422
    assert default.json()["period"] == "30d"
    assert default.json()["since"] == "2025-12-12T00:00:00Z"
