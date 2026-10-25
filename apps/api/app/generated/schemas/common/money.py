# Generated from schemas/ by `make gen-schemas`. Do not edit.

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Money(BaseModel):
    """
    An amount as printed, with its currency.
    """

    model_config = ConfigDict(
        extra='forbid',
    )
    amount: float | None = Field(
        ..., description='The amount as a number, without currency symbols or thousands separators.'
    )
    currency: str | None = Field(..., description='ISO 4217 code, e.g. INR.', pattern='^[A-Z]{3}$')
