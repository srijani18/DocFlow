"""Access token API (F12 plan §3)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ApiTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    expires_in_days: Literal[30, 90, 365] = 90


class ApiToken(BaseModel):
    id: uuid.UUID
    name: str
    prefix: str = Field(description="The token's first characters, to tell tokens apart")
    created_by: str | None = Field(description="The creator's email")
    created_at: datetime
    expires_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None
    active: bool = Field(
        description="Unrevoked, unexpired, and its creator is still a member of the workspace"
    )


class ApiTokenCreated(ApiToken):
    token: str = Field(description="The token itself. Shown only in this response.")
