"""Gateway request, response and error types (ADR-0003)."""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

Task = Literal["classify", "extract"]


@dataclass(frozen=True)
class Prompt:
    task: str
    version: str  # e.g. "classify/v1", recorded on every call and extraction
    text: str


@dataclass(frozen=True)
class TextPart:
    text: str


@dataclass(frozen=True)
class FilePart:
    mime_type: str
    data: bytes


@dataclass(frozen=True)
class CallContext:
    """Who and what a call is for; every llm_calls row carries it (constitution §5.2)."""

    workspace_id: uuid.UUID
    document_id: uuid.UUID | None
    job_id: uuid.UUID | None
    attempt: int


@dataclass(frozen=True)
class LlmRequest:
    task: Task
    prompt: Prompt
    parts: Sequence[TextPart | FilePart]
    # The bundled JSON Schema the answer must satisfy; adapted per provider before sending,
    # but always validated in its original, stricter form.
    response_schema: Mapping[str, Any]
    context: CallContext


@dataclass(frozen=True)
class ProviderRequest:
    model: str
    instructions: str
    parts: Sequence[TextPart | FilePart]
    response_schema: Mapping[str, Any]


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    model: str  # the concrete model that answered (an alias like *-latest resolves to one)
    input_tokens: int | None
    output_tokens: int | None
    truncated: bool = False


@dataclass(frozen=True)
class LlmResult:
    data: dict[str, Any]
    raw_json: str  # the answer exactly as returned, for exact-decimal storage (F5)
    call_id: uuid.UUID
    model: str
    prompt_version: str


class LlmError(Exception):
    """Base for gateway failures. The pipeline maps them to queue errors."""


class TransientLlmError(LlmError):
    """Rate limit, timeout or server error: try again later."""

    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class PermanentLlmError(LlmError):
    """The provider rejected the input itself (e.g. an unreadable file)."""


class InvalidOutputError(LlmError):
    """The answer didn't match the schema. Retried like a transient error (F4 AC2)."""
