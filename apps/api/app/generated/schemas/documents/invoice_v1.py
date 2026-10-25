# Generated from schemas/ by `make gen-schemas`. Do not edit.

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from ..common import money, party


class Type(StrEnum):
    """
    Tax kind, or null if not stated.
    """

    CGST = 'CGST'
    SGST = 'SGST'
    IGST = 'IGST'
    CESS = 'CESS'
    OTHER = 'OTHER'


class LineItem(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    description: str | None = Field(..., description='What was sold.')
    hsn_sac: str | None = Field(..., description='HSN or SAC code.')
    quantity: float | None = Field(..., description='Quantity.')
    unit_price: money.Money | None = Field(..., description='Price per unit.')
    amount: money.Money | None = Field(..., description='Line total.')


class Tax(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    type: Type | None = Field(..., description='Tax kind, or null if not stated.')
    rate_percent: float | None = Field(..., description='Rate in percent, e.g. 9 for 9%.')
    amount: money.Money | None = Field(..., description='Tax amount.')


class Invoice(BaseModel):
    """
    A tax invoice or bill from a seller.
    """

    model_config = ConfigDict(
        extra='forbid',
    )
    invoice_number: str | None = Field(..., description='Invoice number as printed.')
    invoice_date: date | None = Field(..., description='Invoice date (YYYY-MM-DD).')
    due_date: date | None = Field(..., description='Payment due date (YYYY-MM-DD).')
    vendor: party.Party | None = Field(..., description='The seller who issued the invoice.')
    buyer: party.Party | None = Field(..., description='The customer billed.')
    place_of_supply: str | None = Field(..., description='GST place of supply (state).')
    currency: str | None = Field(..., description='ISO 4217 code, e.g. INR.', pattern='^[A-Z]{3}$')
    line_items: list[LineItem] = Field(..., description='Each billed line, in order.')
    subtotal: money.Money | None = Field(..., description='Total before tax.')
    taxes: list[Tax] = Field(..., description='Each tax line (CGST, SGST, IGST…).')
    total: money.Money | None = Field(..., description='Grand total payable.')
