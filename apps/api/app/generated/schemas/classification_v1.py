# Generated from schemas/ by `make gen-schemas`. Do not edit.

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class DocType(Enum):
    """
    invoice, receipt, purchase_order, or other for anything else.
    """

    invoice = 'invoice'
    receipt = 'receipt'
    purchase_order = 'purchase_order'
    other = 'other'


class Classification(BaseModel):
    """
    What kind of document this is, and how sure the model is.
    """

    model_config = ConfigDict(
        extra='forbid',
    )
    doc_type: DocType = Field(
        ..., description='invoice, receipt, purchase_order, or other for anything else.'
    )
    confidence: float = Field(
        ..., description='Probability from 0 to 1 that doc_type is correct.', ge=0.0, le=1.0
    )
