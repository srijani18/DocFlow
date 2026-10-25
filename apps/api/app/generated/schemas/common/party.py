# Generated from schemas/ by `make gen-schemas`. Do not edit.

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from . import address as address_1


class Party(BaseModel):
    """
    A seller, buyer or merchant.
    """

    model_config = ConfigDict(
        extra='forbid',
    )
    name: str | None = Field(..., description='Legal or trading name.')
    gstin: str | None = Field(
        ...,
        description='15-character Indian GSTIN, or null if absent.',
        pattern='^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$',
    )
    address: address_1.Address | None = Field(..., description='Postal address, or null if absent.')
