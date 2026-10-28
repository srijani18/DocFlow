"""Workspace metrics, computed on request (F13 D1)."""

from datetime import UTC, date, datetime, time, timedelta
from typing import get_args

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import WorkspaceScope
from app.documents.models import DocType, Document, DocumentStatus
from app.llm.models import OUTCOMES
from app.llm.types import Task
from app.metrics import repository
from app.metrics.schemas import (
    DayCount,
    FailureReason,
    Headline,
    ModelShare,
    Period,
    Queue,
    TaskReliability,
    Volume,
    WorkspaceMetrics,
)

PERIOD_DAYS: dict[Period, int | None] = {"7d": 7, "30d": 30, "all": None}
TOP_FAILURE_REASONS = 5
UNCLASSIFIED = "unclassified"
UNKNOWN_REASON = "Unknown"


def period_start(period: Period, now: datetime) -> datetime | None:
    """Midnight UTC at the start of the period, so the last N days are N whole days."""
    days = PERIOD_DAYS[period]
    if days is None:
        return None
    first_day = now.astimezone(UTC).date() - timedelta(days=days - 1)
    return datetime.combine(first_day, time.min, UTC)


def _rate(part: int, whole: int) -> float | None:
    return part / whole if whole else None


async def workspace_metrics(
    session: AsyncSession, scope: WorkspaceScope, period: Period, now: datetime
) -> WorkspaceMetrics:
    since = period_start(period, now)
    return WorkspaceMetrics(
        period=period,
        since=since,
        headline=await _headline(session, scope, since),
        volume=await _volume(session, scope, since, today=now.astimezone(UTC).date()),
        llm=await _llm(session, scope, since),
        queue=await _queue(session, scope, since, now),
    )


async def _headline(
    session: AsyncSession, scope: WorkspaceScope, since: datetime | None
) -> Headline:
    approvals = await repository.approvals(session, scope, since)
    fields, changed = await repository.reviewed_fields(session, scope, since)
    cost, documents = await repository.ai_cost(session, scope, since)
    times = await repository.processing_times(session, scope, since)
    without_edits = approvals.approved - approvals.edited
    return Headline(
        approved=approvals.approved,
        approved_without_edits=without_edits,
        approved_by_agent=approvals.by_agent,
        approved_without_edits_rate=_rate(without_edits, approvals.approved),
        fields_reviewed=fields,
        fields_unchanged=fields - changed,
        field_accuracy=_rate(fields - changed, fields),
        documents_processed=documents,
        cost_usd=float(cost) if cost is not None else None,
        cost_per_document_usd=float(cost) / documents if cost is not None and documents else None,
        processing_runs=times.runs,
        processing_seconds_p50=times.p50_seconds,
        processing_seconds_p95=times.p95_seconds,
    )


async def _volume(
    session: AsyncSession, scope: WorkspaceScope, since: datetime | None, *, today: date
) -> Volume:
    per_day = await repository.uploads_per_day(session, scope, since)
    first = since.date() if since is not None else min(per_day, default=today)
    days = [first + timedelta(days=n) for n in range((today - first).days + 1)]
    by_status = await repository.uploaded_by(session, scope, since, Document.status)
    by_doc_type = await repository.uploaded_by(session, scope, since, Document.doc_type)
    return Volume(
        per_day=[DayCount(date=day, uploaded=per_day.get(day, 0)) for day in days]
        if per_day
        else [],
        by_status={status: by_status.get(status, 0) for status in DocumentStatus},
        by_doc_type={doc_type: by_doc_type.get(doc_type, 0) for doc_type in DocType}
        | {UNCLASSIFIED: by_doc_type.get(None, 0)},
    )


async def _llm(
    session: AsyncSession, scope: WorkspaceScope, since: datetime | None
) -> list[TaskReliability]:
    outcomes = await repository.llm_outcomes(session, scope, since)
    served_by = await repository.llm_served_by(session, scope, since)
    latency = await repository.llm_latency(session, scope, since)
    tasks = []
    for task in get_args(Task):
        counts = dict.fromkeys(OUTCOMES, 0)
        for row_task, outcome, calls in outcomes:
            if row_task == task:
                counts[outcome] = calls
        served = [row for row in served_by if row.task == task]
        answers = sum(row.calls for row in served)
        tasks.append(
            TaskReliability(
                task=task,
                calls=sum(counts.values()),
                outcomes=counts,
                fallback_rate=_rate(sum(row.fallbacks for row in served), answers),
                served_by=[
                    ModelShare(provider=row.provider, model=row.model, calls=row.calls)
                    for row in served
                ],
                latency_ms_p50=latency.get(task),
            )
        )
    return tasks


async def _queue(
    session: AsyncSession, scope: WorkspaceScope, since: datetime | None, now: datetime
) -> Queue:
    jobs = await repository.queue(session, scope)
    reasons = await repository.failures(session, scope, since)
    oldest = jobs.oldest_queued_at
    return Queue(
        queued=jobs.by_status.get("queued", 0),
        running=jobs.by_status.get("running", 0),
        dead=jobs.by_status.get("dead", 0),
        oldest_queued_seconds=max((now - oldest).total_seconds(), 0) if oldest else None,
        failed=sum(documents for _, documents in reasons),
        failure_reasons=[
            FailureReason(reason=reason or UNKNOWN_REASON, documents=documents)
            for reason, documents in reasons[:TOP_FAILURE_REASONS]
        ],
    )
