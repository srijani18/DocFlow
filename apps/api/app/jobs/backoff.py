"""Retry delays (F3 spec D1): 30 s, 1 min, 2 min, 4 min… capped at 15 min, ±20% jitter."""

import random

BASE_SECONDS = 30.0
CAP_SECONDS = 15 * 60.0
JITTER = 0.2


def backoff_seconds(
    attempt: int, *, retry_after_seconds: float | None = None, rng: random.Random | None = None
) -> float:
    """Delay before the next try, after `attempt` (1-based) has failed.

    Jitter spreads retries out so jobs that failed together don't retry together. A
    provider's "retry after" wins when it asks for longer.
    """
    rng = rng or random.Random()  # noqa: S311  # jitter, not cryptography
    delay: float = min(BASE_SECONDS * 2.0 ** (attempt - 1), CAP_SECONDS)
    delay *= rng.uniform(1 - JITTER, 1 + JITTER)
    if retry_after_seconds is not None:
        delay = max(delay, retry_after_seconds)
    return delay
