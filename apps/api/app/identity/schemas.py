"""API models for identity endpoints (F1 plan §2). Pydantic, generated into openapi.json."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


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


WorkspaceName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
]


class WorkspaceUpdate(BaseModel):
    """Trimmed on the server, then 1..80 characters (AC16, AC18)."""

    model_config = ConfigDict(extra="forbid")

    name: WorkspaceName
