"""How a processing step tells the queue what to do with a failure (F3 plan §4).

`reason` is shown to users on a FAILED document, so it is a fixed, readable sentence.
Technical detail goes in `detail`, which is stored in `jobs.last_error` and logged.
"""


class StepError(Exception):
    def __init__(self, reason: str, *, detail: str | None = None, code: str | None = None) -> None:
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail or reason
        # Stored as documents.failure_code, e.g. no_ai_key (F15 AC7, AC8).
        self.code = code


class TransientError(StepError):
    """Worth retrying later: timeouts, rate limits, 5xx, a service briefly unavailable."""

    def __init__(
        self, reason: str, *, detail: str | None = None, retry_after_seconds: float | None = None
    ) -> None:
        super().__init__(reason, detail=detail)
        self.retry_after_seconds = retry_after_seconds


class PermanentError(StepError):
    """Retrying can't help: a corrupt or tampered file, an unsupported document."""
