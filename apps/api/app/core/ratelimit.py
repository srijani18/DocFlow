"""Per-user and per-token rate limits (F14 AC9, AC10, plan §4).

Token buckets in process memory: there is one API process (ADR-0002), so this is exact. A
second instance would need shared counters (Postgres or Redis); that is a known limit (D3).
A restart resets the counters.
"""

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from app.core.config import Settings
from app.core.errors import AppError

Bucket = Literal["general", "uploads", "ai", "mcp"]
MAX_TRACKED = 10_000  # (bucket, subject) pairs kept; full buckets are dropped beyond this


class TooManyRequestsError(AppError):
    status = 429
    type_slug = "rate-limited"
    title = "Too many requests"


@dataclass
class _State:
    tokens: float
    updated: float


class RateLimiter:
    def __init__(
        self, per_minute: dict[Bucket, int], clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._per_minute = per_minute
        self._clock = clock
        self._states: dict[tuple[Bucket, str], _State] = {}

    @classmethod
    def from_settings(cls, settings: Settings) -> "RateLimiter":
        return cls(
            {
                "general": settings.rate_limit_general_per_minute,
                "uploads": settings.rate_limit_uploads_per_minute,
                "ai": settings.rate_limit_ai_per_minute,
                "mcp": settings.rate_limit_mcp_per_minute,
            }
        )

    def check(self, bucket: Bucket, subject: str) -> None:
        """Take one token, or raise 429 with how long until the next one."""
        capacity = self._per_minute[bucket]
        refill_per_second = capacity / 60
        now = self._clock()
        state = self._states.get((bucket, subject))
        if state is None:
            if len(self._states) >= MAX_TRACKED:
                self._forget_idle(now)
            state = self._states[(bucket, subject)] = _State(tokens=capacity, updated=now)
        state.tokens = min(capacity, state.tokens + (now - state.updated) * refill_per_second)
        state.updated = now
        if state.tokens >= 1:
            state.tokens -= 1
            return
        wait = math.ceil((1 - state.tokens) / refill_per_second)
        raise TooManyRequestsError(
            f"Too many requests. Try again in {wait} s.", headers={"Retry-After": str(wait)}
        )

    def _forget_idle(self, now: float) -> None:
        # A bucket that would be full again carries no information.
        for key, state in list(self._states.items()):
            capacity = self._per_minute[key[0]]
            if state.tokens + (now - state.updated) * capacity / 60 >= capacity:
                del self._states[key]
