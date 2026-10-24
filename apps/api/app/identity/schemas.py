"""API models for identity endpoints (F1 plan §2). Pydantic, generated into openapi.json."""

import uuid
from enum import StrEnum

from pydantic import BaseModel


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
