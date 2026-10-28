"""API models for review (F7 plan §1)."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SaveCorrections(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_version: int = Field(ge=1, description="The extraction version the edits were made on")
    data: dict[str, Any] = Field(description="The whole corrected instance")


class ApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1, description="The extraction version being approved")
    data: dict[str, Any] | None = Field(
        default=None, description="Unsaved corrections, saved before approving"
    )
    accept_errors: bool = Field(
        default=False, description="Approve even though checks found errors"
    )


class ReviewMetrics(BaseModel):
    approved: int
    approved_without_edits: int
    approved_by_agent: int
    approved_without_edits_rate: float | None = Field(
        description="approved_without_edits / approved; null when nothing is approved yet"
    )
