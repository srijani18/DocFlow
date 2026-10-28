"""Metrics response (F13 plan §1)."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Period = Literal["7d", "30d", "all"]


class Headline(BaseModel):
    """The four headline metrics (constitution §10.2)."""

    approved: int
    approved_without_edits: int
    approved_by_agent: int
    approved_without_edits_rate: float | None = Field(
        description="approved_without_edits / approved; null when nothing was approved"
    )
    fields_reviewed: int = Field(description="Fields on documents a person approved")
    fields_unchanged: int
    field_accuracy: float | None = Field(
        description="fields_unchanged / fields_reviewed; agent approvals are not included"
    )
    documents_processed: int = Field(description="Documents with AI calls in the period")
    cost_usd: float | None = Field(description="Estimated at list prices")
    cost_per_document_usd: float | None
    processing_runs: int = Field(description="Processing runs that finished in the period")
    processing_seconds_p50: float | None
    processing_seconds_p95: float | None


class DayCount(BaseModel):
    date: date
    uploaded: int


class Volume(BaseModel):
    per_day: list[DayCount] = Field(description="Every day of the period, oldest first")
    by_status: dict[str, int] = Field(
        description="Documents uploaded in the period, by their status now"
    )
    by_doc_type: dict[str, int] = Field(description="As by_status; 'unclassified' when unknown")


class ModelShare(BaseModel):
    provider: str
    model: str
    calls: int


class TaskReliability(BaseModel):
    task: str
    calls: int
    outcomes: dict[str, int] = Field(description="Every outcome, zero included")
    fallback_rate: float | None = Field(
        description="Share of answers that came from a fallback in the route"
    )
    served_by: list[ModelShare] = Field(description="Answers (fresh or cached), most first")
    latency_ms_p50: float | None = Field(description="Of fresh answers")


class FailureReason(BaseModel):
    reason: str
    documents: int


class Queue(BaseModel):
    queued: int
    running: int
    dead: int
    oldest_queued_seconds: float | None
    failed: int = Field(description="Documents that failed in the period")
    failure_reasons: list[FailureReason] = Field(description="The most common, at most 5")


class WorkspaceMetrics(BaseModel):
    period: Period
    since: datetime | None = Field(description="Start of the period; null for all time")
    headline: Headline
    volume: Volume
    llm: list[TaskReliability]
    queue: Queue
