import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class Extraction(BaseModel):
    """One version of a document's extracted data (ADR-0005)."""

    id: uuid.UUID
    version: int
    source: Literal["model", "agent_fix", "human"]
    schema_id: str = Field(
        description="The schema `data` was validated against, e.g. docflow/invoice/v1"
    )
    data: dict[str, Any]
    confidence: dict[str, float] = Field(
        description="Field path (dotted, zero-based indices) to a score from 0 to 1"
    )
    prompt_version: str | None
    created_at: datetime
