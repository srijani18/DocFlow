"""A gateway wired to a scripted provider, for pipeline tests."""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.llm.gateway import Credentials, Gateway
from app.llm.providers.fake import FakeProvider, Script
from app.llm.routing import RouteEntry


@dataclass
class StaticCredentials:
    """Every workspace has these keys, unless listed in `without`."""

    keys: Mapping[str, str] = field(default_factory=lambda: {"fake": "fake-key"})
    without: set[uuid.UUID] = field(default_factory=set)
    rejected: list[tuple[uuid.UUID, str]] = field(default_factory=list)

    async def keys_for(self, workspace_id: uuid.UUID) -> Mapping[str, str]:
        return {} if workspace_id in self.without else self.keys

    async def mark_rejected(self, workspace_id: uuid.UUID, provider: str) -> None:
        self.rejected.append((workspace_id, provider))


def fake_gateway(
    sessionmaker: async_sessionmaker[AsyncSession],
    script: Script,
    credentials: Credentials | None = None,
) -> tuple[Gateway, FakeProvider]:
    provider = FakeProvider(script)
    gateway = Gateway(
        sessionmaker=sessionmaker,
        providers={"fake": provider},
        routes={
            "classify": (RouteEntry("fake", "fake-model"),),
            "extract": (RouteEntry("fake", "fake-model"),),
            "validate": (RouteEntry("fake", "fake-model"),),
            "embed": (RouteEntry("fake", "fake-embedding"),),
        },
        credentials=credentials or StaticCredentials(),
    )
    return gateway, provider


def answers(*replies: Any) -> Script:
    """A script that gives these replies in order, repeating the last one."""
    remaining = list(replies)

    def script(_request: Any) -> Any:
        return remaining.pop(0) if len(remaining) > 1 else remaining[0]

    return script
