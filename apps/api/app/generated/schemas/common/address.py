# Generated from schemas/ by `make gen-schemas`. Do not edit.

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Address(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    line1: str | None = Field(..., description='First address line.')
    line2: str | None = Field(..., description='Second address line.')
    city: str | None = Field(..., description='City.')
    state: str | None = Field(..., description='State or province.')
    postal_code: str | None = Field(..., description='PIN or postal code.')
    country: str | None = Field(..., description='Country.')
