"""A gateway wired to a scripted provider, for pipeline tests."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.llm.gateway import Gateway, Route
from app.llm.providers.fake import FakeProvider, Script


def fake_gateway(
    sessionmaker: async_sessionmaker[AsyncSession], script: Script
) -> tuple[Gateway, FakeProvider]:
    provider = FakeProvider(script)
    gateway = Gateway(
        sessionmaker=sessionmaker,
        providers={"fake": provider},
        routes={"classify": Route("fake", "fake-model"), "extract": Route("fake", "fake-model")},
    )
    return gateway, provider


def answers(*replies: Any) -> Script:
    """A script that gives these replies in order, repeating the last one."""
    remaining = list(replies)

    def script(_request: Any) -> Any:
        return remaining.pop(0) if len(remaining) > 1 else remaining[0]

    return script
