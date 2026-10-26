"""API models for validation issues (F6 plan §4)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ValidationIssue(BaseModel):
    """A failed check on the current extraction, or one the agent fixed on the way to it."""

    id: uuid.UUID
    check_name: str = Field(
        description="line_items, totals, gstin, tax_type, dates, duplicate or known_vendor"
    )
    severity: Literal["error", "warning", "info"]
    paths: list[str] = Field(description="Field paths involved (dotted, zero-based indices)")
    message: str
    fixed_by_agent: bool
    created_at: datetime


class ValidationIssueList(BaseModel):
    items: list[ValidationIssue]
