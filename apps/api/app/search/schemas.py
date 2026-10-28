"""API models for search (F8 plan §1)."""

from typing import Literal

from pydantic import BaseModel, Field

from app.documents.schemas import Document


class SearchHit(BaseModel):
    document: Document
    matched: Literal["keyword", "meaning", "both"] | None = Field(
        description="Why it matched; null when there was no text to match"
    )
    snippet: str | None = Field(
        description="Matching text, with the matched words between [[ and ]]"
    )


class SearchResults(BaseModel):
    items: list[SearchHit]
    next_cursor: str | None
    semantic: bool = Field(
        description="False when matching by meaning was unavailable: keyword matches only"
    )
