from dataclasses import dataclass, field

import pytest
from fastapi import FastAPI

from app.aikeys.checks import CheckResult
from app.aikeys.routes import get_key_checker
from tests.support.clock import FrozenClock


@dataclass
class FakeChecker:
    """Stands in for the provider check; `result` decides what the provider says."""

    clock: FrozenClock
    result: CheckResult = CheckResult.OK
    checked: list[tuple[str, str]] = field(default_factory=list)

    async def check(self, provider: str, key: str) -> CheckResult:
        self.checked.append((provider, key))
        return self.result


@pytest.fixture
def key_checker(clock: FrozenClock) -> FakeChecker:
    return FakeChecker(clock=clock)


@pytest.fixture(autouse=True)
def _use_fake_checker(db_app: FastAPI, key_checker: FakeChecker) -> None:
    db_app.dependency_overrides[get_key_checker] = lambda: key_checker
