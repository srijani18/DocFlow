"""SQL for the workspace metrics (F13 plan §2).

Every query starts from `workspace_id`, and each answers one block of the page. `since` is
the start of the period, or None for all time.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, Integer, cast, distinct, func, literal, select
from sqlalchemy.dialects.postgresql import JSONPATH
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import QueryableAttribute, aliased

from app.core.tenancy import WorkspaceScope
from app.documents.models import Document, DocumentEvent, DocumentStatus
from app.extractions.models import Extraction
from app.jobs.models import Job
from app.llm.models import LlmCall
from app.review.models import Correction

FINISHED = (DocumentStatus.NEEDS_REVIEW, DocumentStatus.APPROVED, DocumentStatus.FAILED)
SERVED = ("ok", "cache_hit")  # outcomes that produced an answer
# Every scalar value in an extraction, nulls included: what a reviewer could change.
# Strict mode, so arrays aren't unwrapped (and their items counted twice).
LEAVES = 'strict $.** ? (@.type() != "object" && @.type() != "array")'


def _from(column: QueryableAttribute[Any], since: datetime | None) -> ColumnElement[bool]:
    return column >= since if since is not None else literal(True)


@dataclass(frozen=True)
class Approvals:
    approved: int
    edited: int
    by_agent: int


async def approvals(
    session: AsyncSession, scope: WorkspaceScope, since: datetime | None
) -> Approvals:
    """Documents approved in the period: all, those with a correction, those by the agent."""
    edited = (
        select(Correction.id)
        .where(Correction.workspace_id == scope.workspace_id, Correction.document_id == Document.id)
        .exists()
    )
    row = (
        await session.execute(
            select(
                func.count(),
                func.count().filter(edited),
                func.count().filter(Document.approved_by_agent.is_(True)),
            ).where(
                Document.workspace_id == scope.workspace_id,
                Document.status == DocumentStatus.APPROVED,
                _from(Document.approved_at, since),
            )
        )
    ).one()
    return Approvals(approved=row[0], edited=row[1], by_agent=row[2])


async def reviewed_fields(
    session: AsyncSession, scope: WorkspaceScope, since: datetime | None
) -> tuple[int, int]:
    """(fields, fields a reviewer changed) on documents a person approved in the period."""
    leaves = cast(literal(LEAVES), JSONPATH)
    fields = func.jsonb_array_length(func.jsonb_path_query_array(Extraction.data, leaves))
    changed = (
        select(func.count(distinct(Correction.path)))
        .where(Correction.workspace_id == scope.workspace_id, Correction.document_id == Document.id)
        .scalar_subquery()
    )
    row = (
        await session.execute(
            select(
                func.coalesce(func.sum(fields), 0),
                # A removed table row is a change to fields the approved version no longer has.
                func.coalesce(func.sum(func.least(changed, fields)), 0),
            )
            .select_from(Document)
            .join(Extraction, Extraction.id == Document.approved_extraction_id)
            .where(
                Document.workspace_id == scope.workspace_id,
                Extraction.workspace_id == scope.workspace_id,
                Document.status == DocumentStatus.APPROVED,
                Document.approved_by_user_id.is_not(None),
                _from(Document.approved_at, since),
            )
        )
    ).one()
    return int(row[0]), int(row[1])


@dataclass(frozen=True)
class ProcessingTimes:
    runs: int
    p50_seconds: float | None
    p95_seconds: float | None


async def processing_times(
    session: AsyncSession, scope: WorkspaceScope, since: datetime | None
) -> ProcessingTimes:
    """Each document's latest run (its last UPLOADED event, so a retry starts a new one) to
    the first later event into a finished status. Runs that finished in the period count."""
    start = (
        select(DocumentEvent.document_id, func.max(DocumentEvent.id).label("event_id"))
        .where(
            DocumentEvent.workspace_id == scope.workspace_id,
            DocumentEvent.to_status == DocumentStatus.UPLOADED,
        )
        .group_by(DocumentEvent.document_id)
        .subquery()
    )
    started = aliased(DocumentEvent)
    finished = aliased(DocumentEvent)
    finished_at = (
        select(finished.created_at)
        .where(
            finished.workspace_id == scope.workspace_id,
            finished.document_id == start.c.document_id,
            finished.id > start.c.event_id,
            finished.to_status.in_(FINISHED),
        )
        .order_by(finished.id)
        .limit(1)
        .correlate(start)
        .scalar_subquery()
    )
    runs = (
        select(started.created_at.label("started_at"), finished_at.label("finished_at"))
        .join_from(start, started, started.id == start.c.event_id)
        .subquery()
    )
    seconds = func.extract("epoch", runs.c.finished_at - runs.c.started_at)
    row = (
        await session.execute(
            select(
                func.count(),
                func.percentile_cont(0.5).within_group(seconds),
                func.percentile_cont(0.95).within_group(seconds),
            ).where(
                runs.c.finished_at.is_not(None),
                runs.c.finished_at >= since if since is not None else literal(True),
            )
        )
    ).one()
    return ProcessingTimes(runs=row[0], p50_seconds=row[1], p95_seconds=row[2])


async def ai_cost(
    session: AsyncSession, scope: WorkspaceScope, since: datetime | None
) -> tuple[Decimal | None, int]:
    """(estimated cost, documents) of LLM calls made for documents in the period."""
    row = (
        await session.execute(
            select(func.sum(LlmCall.cost_usd), func.count(distinct(LlmCall.document_id))).where(
                LlmCall.workspace_id == scope.workspace_id,
                LlmCall.document_id.is_not(None),
                _from(LlmCall.created_at, since),
            )
        )
    ).one()
    return row[0], row[1]


async def uploads_per_day(
    session: AsyncSession, scope: WorkspaceScope, since: datetime | None
) -> dict[date, int]:
    day = func.date(func.timezone("UTC", Document.created_at))
    rows = await session.execute(
        select(day, func.count())
        .where(
            Document.workspace_id == scope.workspace_id,
            _from(Document.created_at, since),
        )
        .group_by(day)
    )
    return {row[0]: row[1] for row in rows}


async def uploaded_by(
    session: AsyncSession,
    scope: WorkspaceScope,
    since: datetime | None,
    column: QueryableAttribute[Any],
) -> dict[str | None, int]:
    """Documents uploaded in the period, counted by one of their columns as it is now."""
    rows = await session.execute(
        select(column, func.count())
        .where(
            Document.workspace_id == scope.workspace_id,
            _from(Document.created_at, since),
        )
        .group_by(column)
    )
    return {row[0]: row[1] for row in rows}


@dataclass(frozen=True)
class ServedBy:
    task: str
    provider: str
    model: str
    calls: int
    fallbacks: int


async def llm_outcomes(
    session: AsyncSession, scope: WorkspaceScope, since: datetime | None
) -> list[tuple[str, str, int]]:
    """(task, outcome, calls) in the period."""
    rows = await session.execute(
        select(LlmCall.task, LlmCall.outcome, func.count())
        .where(
            LlmCall.workspace_id == scope.workspace_id,
            _from(LlmCall.created_at, since),
        )
        .group_by(LlmCall.task, LlmCall.outcome)
    )
    return [(row[0], row[1], row[2]) for row in rows]


async def llm_served_by(
    session: AsyncSession, scope: WorkspaceScope, since: datetime | None
) -> list[ServedBy]:
    """Answers (fresh or cached) by task, provider and model, and how many were fallbacks."""
    rows = await session.execute(
        select(
            LlmCall.task,
            LlmCall.provider,
            LlmCall.model,
            func.count(),
            func.sum(cast(LlmCall.fallback, Integer)),
        )
        .where(
            LlmCall.workspace_id == scope.workspace_id,
            LlmCall.outcome.in_(SERVED),
            _from(LlmCall.created_at, since),
        )
        .group_by(LlmCall.task, LlmCall.provider, LlmCall.model)
        .order_by(LlmCall.task, func.count().desc(), LlmCall.provider, LlmCall.model)
    )
    return [ServedBy(*row) for row in rows]


async def llm_latency(
    session: AsyncSession, scope: WorkspaceScope, since: datetime | None
) -> dict[str, float]:
    """Median latency of fresh answers by task (cache hits would flatter it)."""
    rows = await session.execute(
        select(LlmCall.task, func.percentile_cont(0.5).within_group(LlmCall.latency_ms))
        .where(
            LlmCall.workspace_id == scope.workspace_id,
            LlmCall.outcome == "ok",
            _from(LlmCall.created_at, since),
        )
        .group_by(LlmCall.task)
    )
    return {row[0]: row[1] for row in rows}


@dataclass(frozen=True)
class Queue:
    by_status: dict[str, int]
    oldest_queued_at: datetime | None


async def queue(session: AsyncSession, scope: WorkspaceScope) -> Queue:
    """The queue now: jobs waiting, running or given up on."""
    rows = await session.execute(
        select(Job.status, func.count(), func.min(Job.created_at))
        .where(Job.workspace_id == scope.workspace_id, Job.status != "succeeded")
        .group_by(Job.status)
    )
    by_status: dict[str, int] = {}
    oldest_queued_at = None
    for status, count, oldest in rows:
        by_status[status] = count
        if status == "queued":
            oldest_queued_at = oldest
    return Queue(by_status=by_status, oldest_queued_at=oldest_queued_at)


async def failures(
    session: AsyncSession, scope: WorkspaceScope, since: datetime | None
) -> list[tuple[str | None, int]]:
    """Documents that failed in the period, by reason, most common first."""
    count = func.count()
    rows = await session.execute(
        select(Document.failure_reason, count)
        .where(
            Document.workspace_id == scope.workspace_id,
            Document.status == DocumentStatus.FAILED,
            _from(Document.status_changed_at, since),
        )
        .group_by(Document.failure_reason)
        .order_by(count.desc(), Document.failure_reason)
    )
    return [(row[0], row[1]) for row in rows]
