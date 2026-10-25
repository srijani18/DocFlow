# Generated from schemas/ by `make gen-schemas`. Do not edit.

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConfidenceItem(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    field: str = Field(
        ...,
        description='Dotted path with zero-based indices, e.g. vendor.gstin or line_items.0.amount.amount.',
    )
    score: float = Field(
        ..., description='Probability from 0 to 1 that the value is correct.', ge=0.0, le=1.0
    )


class ExtractionEnvelope(BaseModel):
    """
    What the model returns: the document data plus a confidence per field. `data` is checked against the document type's own schema.
    """

    model_config = ConfigDict(
        extra='forbid',
    )
    data: dict[str, Any] = Field(..., description="An instance of the document type's schema.")
    confidence: list[ConfidenceItem] = Field(
        ..., description='How sure the model is about each extracted field.'
    )
