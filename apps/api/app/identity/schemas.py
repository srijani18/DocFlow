"""API models for identity endpoints (F1 plan §2). Pydantic, generated into openapi.json."""

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Role(StrEnum):
    ADMIN = "admin"
    REVIEWER = "reviewer"


class User(BaseModel):
    id: uuid.UUID
    email: str | None
    display_name: str | None


class WorkspaceSummary(BaseModel):
    id: uuid.UUID
    name: str


class Membership(BaseModel):
    workspace: WorkspaceSummary
    role: Role


class Me(BaseModel):
    user: User
    memberships: list[Membership]


class Workspace(BaseModel):
    id: uuid.UUID
    name: str = Field(min_length=1, max_length=80)
    role: Role = Field(description="The caller's role in this workspace.")
    created_at: datetime
