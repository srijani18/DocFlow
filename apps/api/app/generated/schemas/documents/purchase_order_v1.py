# Generated from schemas/ by `make gen-schemas`. Do not edit.

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from ..common import money, party


class LineItem(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    description: str | None = Field(..., description='What was sold.')
    hsn_sac: str | None = Field(..., description='HSN or SAC code.')
    quantity: float | None = Field(..., description='Quantity.')
    unit_price: money.Money | None = Field(..., description='Price per unit.')
    amount: money.Money | None = Field(..., description='Line total.')


class Type(StrEnum):
    """
    Tax kind, or null if not stated.
    """

    CGST = 'CGST'
    SGST = 'SGST'
    IGST = 'IGST'
    CESS = 'CESS'
    OTHER = 'OTHER'


class Tax(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    type: Type | None = Field(..., description='Tax kind, or null if not stated.')
    rate_percent: float | None = Field(..., description='Rate in percent, e.g. 9 for 9%.')
    amount: money.Money | None = Field(..., description='Tax amount.')


class PurchaseOrder(BaseModel):
    """
    A buyer's order to a supplier.
    """

    model_config = ConfigDict(
        extra='forbid',
    )
    po_number: str | None = Field(..., description='Purchase order number.')
    po_date: date | None = Field(..., description='Order date (YYYY-MM-DD).')
    delivery_date: date | None = Field(..., description='Requested delivery date (YYYY-MM-DD).')
    buyer: party.Party | None = Field(..., description='The company placing the order.')
    vendor: party.Party | None = Field(..., description='The supplier.')
    currency: str | None = Field(..., description='ISO 4217 code, e.g. INR.', pattern='^[A-Z]{3}$')
    line_items: list[LineItem] = Field(..., description='Each ordered line, in order.')
    subtotal: money.Money | None = Field(..., description='Total before tax.')
    taxes: list[Tax] = Field(..., description='Each tax line.')
    total: money.Money | None = Field(..., description='Order total.')
