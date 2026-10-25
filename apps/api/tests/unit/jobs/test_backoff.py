import random

from app.jobs.backoff import backoff_seconds


class FixedRandom(random.Random):
    def __init__(self, value: float) -> None:
        super().__init__()
        self._value = value

    def uniform(self, a: float, b: float) -> float:
        return a + (b - a) * self._value


def test_ac3_backoff_doubles_with_cap_and_retry_after() -> None:
    middle = FixedRandom(0.5)  # no jitter
    assert [backoff_seconds(n, rng=middle) for n in (1, 2, 3, 4, 5, 6, 10)] == [
        30,
        60,
        120,
        240,
        480,
        900,
        900,
    ]
    # Jitter stays within ±20%.
    assert backoff_seconds(1, rng=FixedRandom(0.0)) == 24
    assert backoff_seconds(1, rng=FixedRandom(1.0)) == 36
    # A provider's "retry after" wins when it is longer, never when shorter.
    assert backoff_seconds(1, retry_after_seconds=90, rng=middle) == 90
    assert backoff_seconds(3, retry_after_seconds=5, rng=middle) == 120
