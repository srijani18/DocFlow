from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Provider(StrEnum):
    GEMINI = "gemini"
    GROQ = "groq"
    OPENROUTER = "openrouter"


class AiKeyStatus(BaseModel):
    """What anyone in the workspace may see about a key. There is no field for the key
    itself, by design (F15 AC4)."""

    provider: Provider
    connected: bool
    last4: str | None
    status: str | None = Field(description="ok | rejected | unchecked")
    checked_at: datetime | None
    updated_at: datetime | None


class AiKeySave(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: str = Field(min_length=8, max_length=512, description="Write-only; never returned")
