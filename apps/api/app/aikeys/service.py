"""Workspaces' own AI keys (F15). Other modules use this facade (ADR-0002)."""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.aikeys import repository
from app.aikeys.checks import CheckResult, check_key
from app.aikeys.crypto import KeyBox, KeyBoxError, Sealed
from app.aikeys.models import PROVIDERS, WorkspaceAiKey
from app.core.clock import Clock
from app.core.errors import AppError, NotFoundError, ServiceUnavailableError
from app.core.logging import get_logger
from app.core.tenancy import WorkspaceScope
from app.documents import service as documents

log = get_logger(__name__)

# Failures that a newly connected key can fix; those documents are requeued (F15 AC8).
REQUEUE_ON_CONNECT = ("no_ai_key", "key_rejected")


class InvalidApiKeyError(AppError):
    status = 422
    type_slug = "invalid-api-key"
    title = "The provider didn't accept this key"


class KeyCheckUnavailableError(ServiceUnavailableError):
    type_slug = "key-check-unavailable"
    title = "Couldn't reach the provider to check the key"


class KeyStorageNotConfiguredError(ServiceUnavailableError):
    type_slug = "key-storage-unavailable"
    title = "Key storage is not configured"


@dataclass(frozen=True)
class KeyChecker:
    """Everything needed to check a key with its provider."""

    http: httpx.AsyncClient
    gemini_base_url: str
    clock: Clock

    async def check(self, provider: str, key: str) -> CheckResult:
        return await check_key(provider, key, http=self.http, gemini_base_url=self.gemini_base_url)


def _require(keybox: KeyBox | None) -> KeyBox:
    if keybox is None:
        raise KeyStorageNotConfiguredError()
    return keybox


def _provider(value: str) -> str:
    if value not in PROVIDERS:
        raise NotFoundError()
    return value


def last4(key: str) -> str:
    return key[-4:] if len(key) >= 8 else "…"  # short keys show nothing


async def list_statuses(session: AsyncSession, scope: WorkspaceScope) -> dict[str, WorkspaceAiKey]:
    return {row.provider: row for row in await repository.list_keys(session, scope)}


async def save_key(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    keybox: KeyBox | None,
    checker: KeyChecker,
    provider: str,
    api_key: str,
) -> tuple[WorkspaceAiKey, list[documents.StatusEvent]]:
    """Check, encrypt and store a key, then requeue documents it can fix (AC1, AC8)."""
    box = _require(keybox)
    provider = _provider(provider)
    api_key = api_key.strip()
    result = await checker.check(provider, api_key)
    if result is CheckResult.REJECTED:
        raise InvalidApiKeyError(f"This doesn't look like a valid {provider} key.")
    if result is CheckResult.UNAVAILABLE:
        raise KeyCheckUnavailableError(f"{provider} didn't answer. Try again in a moment.")
    row = await repository.upsert_key(
        session,
        scope,
        provider=provider,
        sealed=box.seal(scope.workspace_id, api_key),
        last4=last4(api_key),
        status="ok",
        checked_at=checker.clock.now(),
    )
    events = await documents.retry_failed_with_codes(session, scope, REQUEUE_ON_CONNECT)
    log.info("ai_key_saved", provider=provider, requeued=len(events))
    return row, events


async def delete_key(session: AsyncSession, scope: WorkspaceScope, provider: str) -> None:
    if not await repository.delete_key(session, scope, _provider(provider)):
        raise NotFoundError()


async def test_key(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    keybox: KeyBox | None,
    checker: KeyChecker,
    provider: str,
) -> WorkspaceAiKey:
    """Check the stored key again and record the result (AC5)."""
    box = _require(keybox)
    row = await repository.get_key(session, scope, _provider(provider))
    if row is None:
        raise NotFoundError()
    try:
        key = box.open(scope.workspace_id, Sealed(row.ciphertext, row.nonce, row.key_version))
    except KeyBoxError:
        log.error("ai_key_undecryptable", provider=provider)
        status = "rejected"
    else:
        result = await checker.check(provider, key)
        if result is CheckResult.UNAVAILABLE:
            raise KeyCheckUnavailableError(f"{provider} didn't answer. Try again in a moment.")
        status = "ok" if result is CheckResult.OK else "rejected"
    await repository.set_status(
        session, scope, provider, status=status, checked_at=checker.clock.now()
    )
    refreshed = await repository.get_key(session, scope, provider)
    assert refreshed is not None  # noqa: S101  # just updated in this transaction
    return refreshed


class WorkspaceCredentials:
    """The gateway's source of keys (F15 AC6): the document's own workspace only, decrypted
    per call. Without a master key nothing is usable, so documents fail with no_ai_key."""

    def __init__(
        self, *, sessionmaker: async_sessionmaker[AsyncSession], keybox: KeyBox | None
    ) -> None:
        self._sessionmaker = sessionmaker
        self._keybox = keybox

    async def keys_for(self, workspace_id: uuid.UUID) -> Mapping[str, str]:
        if self._keybox is None:
            return {}
        async with self._sessionmaker() as session:
            rows = await repository.usable_keys(session, workspace_id)
        keys: dict[str, str] = {}
        for row in rows:
            try:
                keys[row.provider] = self._keybox.open(
                    workspace_id, Sealed(row.ciphertext, row.nonce, row.key_version)
                )
            except KeyBoxError:
                log.error("ai_key_undecryptable", provider=row.provider)
        return keys

    async def mark_rejected(self, workspace_id: uuid.UUID, provider: str) -> None:
        scope = WorkspaceScope(workspace_id=workspace_id, user_id=uuid.UUID(int=0), role="worker")
        async with self._sessionmaker() as session, session.begin():
            await repository.set_status(
                session, scope, provider, status="rejected", checked_at=datetime.now().astimezone()
            )
        log.warning("ai_key_rejected", provider=provider)
