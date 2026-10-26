"""Turns gateway errors into queue decisions (F3 plan §4) with readable reasons."""

from app.jobs.errors import PermanentError, StepError, TransientError
from app.llm.types import (
    CredentialRejectedError,
    InvalidOutputError,
    LlmError,
    NoCredentialsError,
    PermanentLlmError,
    TransientLlmError,
)

NO_AI_KEY = "no_ai_key"
KEY_REJECTED = "key_rejected"


def to_step_error(exc: LlmError, *, invalid_reason: str) -> StepError:
    if isinstance(exc, NoCredentialsError):
        # Permanent with a code, so no retries are wasted and connecting a key requeues
        # exactly these documents (F15 AC7, AC8).
        return PermanentError("No AI provider key connected", detail=str(exc), code=NO_AI_KEY)
    if isinstance(exc, CredentialRejectedError):
        return PermanentError(
            "The AI provider rejected this workspace's key", detail=str(exc), code=KEY_REJECTED
        )
    if isinstance(exc, TransientLlmError):
        return TransientError(
            "AI service unavailable", detail=str(exc), retry_after_seconds=exc.retry_after_seconds
        )
    if isinstance(exc, InvalidOutputError):
        # A different answer may well be valid, so it is retried (F4 AC2, F5 AC3).
        return TransientError(invalid_reason, detail=f"invalid output: {exc}")
    if isinstance(exc, PermanentLlmError):
        return PermanentError("The AI service couldn't read this file", detail=str(exc))
    return TransientError("AI service unavailable", detail=repr(exc))
