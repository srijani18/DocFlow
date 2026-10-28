# Generated from schemas/ by `make gen-schemas`. Do not edit.

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Fix(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    path: str = Field(..., description='Dotted field path, as given in the request.')
    value: str | float | None = Field(
        ..., description='The value exactly as printed (numbers without separators).'
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    reason: str = Field(..., description='What was misread, briefly.')


class AgentFixes(BaseModel):
    """
    Corrected values the validation agent's model proposes after rereading the document (F6).
    """

    model_config = ConfigDict(
        extra='forbid',
    )
    fixes: list[Fix] = Field(
        ...,
        description='One entry per field whose printed value differs from the current value. Empty if nothing was misread.',
    )
