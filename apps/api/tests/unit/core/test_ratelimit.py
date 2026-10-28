import pytest

from app.core.ratelimit import RateLimiter, TooManyRequestsError


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_ac9_a_full_bucket_allows_a_burst_then_refuses_with_retry_after() -> None:
    clock = Clock()
    limiter = RateLimiter({"general": 3, "uploads": 1, "ai": 1, "mcp": 1}, clock=clock)

    for _ in range(3):
        limiter.check("general", "ada")
    with pytest.raises(TooManyRequestsError) as refused:
        limiter.check("general", "ada")

    assert refused.value.headers == {"Retry-After": "20"}  # 3 a minute: one every 20 s
    assert refused.value.detail == "Too many requests. Try again in 20 s."


def test_ac9_buckets_refill_and_are_separate_per_subject_and_bucket() -> None:
    clock = Clock()
    limiter = RateLimiter({"general": 3, "uploads": 1, "ai": 1, "mcp": 1}, clock=clock)
    limiter.check("uploads", "ada")

    limiter.check("uploads", "grace")  # another user
    limiter.check("ai", "ada")  # another bucket
    with pytest.raises(TooManyRequestsError):
        limiter.check("uploads", "ada")
    clock.now += 60
    limiter.check("uploads", "ada")  # refilled


def test_idle_full_buckets_are_forgotten(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.ratelimit.MAX_TRACKED", 2)
    clock = Clock()
    limiter = RateLimiter({"general": 60, "uploads": 1, "ai": 1, "mcp": 1}, clock=clock)
    limiter.check("general", "a")
    limiter.check("general", "b")
    clock.now += 120

    limiter.check("general", "c")

    assert len(limiter._states) == 1  # a and b were full again
