from app.core.clock import Clock, SystemClock
from tests.support.clock import FrozenClock


def test_frozen_clock_moves_only_when_advanced() -> None:
    clock: Clock = FrozenClock()
    start = clock.now()

    assert clock.now() == start
    assert isinstance(clock, FrozenClock)
    clock.advance(minutes=10)
    assert (clock.now() - start).total_seconds() == 600


def test_system_clock_is_timezone_aware() -> None:
    assert SystemClock().now().tzinfo is not None
