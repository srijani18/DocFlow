"""Rest a provider/model that keeps failing (F10 AC4, spec D2).

closed ──3 consecutive transient failures──▶ open (skipped for 60 s)
open ──60 s later──▶ half-open: one trial request
half-open ──success──▶ closed      half-open ──failure──▶ open again

Kept in memory per process and keyed by (workspace, provider, model), because each
workspace has its own keys and quota (F15). A restart forgets it, which only costs one
failed call.
"""

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

FAILURE_THRESHOLD = 3
OPEN_SECONDS = 60.0

Key = tuple[uuid.UUID, str, str]


@dataclass
class _State:
    failures: int = 0
    opened_at: float | None = None
    trial_in_flight: bool = False


class CircuitBreaker:
    def __init__(
        self,
        *,
        threshold: int = FAILURE_THRESHOLD,
        open_seconds: float = OPEN_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._threshold = threshold
        self._open_seconds = open_seconds
        self._clock = clock
        self._states: dict[Key, _State] = {}

    def allow(self, key: Key) -> bool:
        state = self._states.get(key)
        if state is None or state.opened_at is None:
            return True
        if self._clock() - state.opened_at < self._open_seconds:
            return False
        if state.trial_in_flight:
            return False  # half-open: exactly one trial at a time
        state.trial_in_flight = True
        return True

    def seconds_until_retry(self, key: Key) -> float:
        state = self._states.get(key)
        if state is None or state.opened_at is None:
            return 0.0
        return max(self._open_seconds - (self._clock() - state.opened_at), 0.0)

    def success(self, key: Key) -> None:
        self._states.pop(key, None)

    def failure(self, key: Key) -> None:
        state = self._states.setdefault(key, _State())
        state.failures += 1
        if state.trial_in_flight or state.failures >= self._threshold:
            state.opened_at = self._clock()
            state.trial_in_flight = False

    def release(self, key: Key) -> None:
        """A half-open trial ended without a verdict (e.g. invalid output): allow another."""
        state = self._states.get(key)
        if state is not None:
            state.trial_in_flight = False
