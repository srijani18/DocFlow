# Generated from schemas/ by `make gen-schemas`. Do not edit.

from __future__ import annotations

from datetime import date as date_aliased

from pydantic import BaseModel, ConfigDict, Field

from ..common import money, party


class LineItem(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    description: str | None = Field(..., description='What was bought.')
    quantity: float | None = Field(..., description='Quantity.')
    amount: money.Money | None = Field(..., description='Line total.')


class Receipt(BaseModel):
    """
    Proof of a payment already made, such as a till slip.
    """

    model_config = ConfigDict(
        extra='forbid',
    )
    receipt_number: str | None = Field(..., description='Receipt or bill number.')
    date: date_aliased | None = Field(..., description='Date of payment (YYYY-MM-DD).')
    time: str | None = Field(
        ...,
        description='Time of payment, 24-hour HH:MM.',
        pattern='^([01][0-9]|2[0-3]):[0-5][0-9]$',
    )
    merchant: party.Party | None = Field(..., description='The shop or business that was paid.')
    currency: str | None = Field(..., description='ISO 4217 code, e.g. INR.', pattern='^[A-Z]{3}$')
    line_items: list[LineItem] = Field(..., description='Each purchased line, in order.')
    subtotal: money.Money | None = Field(..., description='Total before tax.')
    tax_total: money.Money | None = Field(..., description='Total tax.')
    total: money.Money | None = Field(..., description='Amount paid.')
    payment_method: str | None = Field(..., description='How it was paid, e.g. cash, card, UPI.')
