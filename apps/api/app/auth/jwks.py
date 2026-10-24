"""Cache of the identity provider's public signing keys (F1 plan §4.2).

- Keys are fetched lazily and cached for `ttl_seconds` (10 min, matching Supabase's own
  edge cache), so a withdrawn key stops working within that window (AC12).
- A token with an unknown `kid` forces a refresh, at most once per
  `min_forced_refresh_seconds`, so random kids can't flood the provider.
- Stale-if-error: if a refresh fails, previously fetched keys keep working (AC13) and the
  next attempt waits `retry_after_failure_seconds` instead of slowing every request.
- The URL comes only from configuration; token headers (`jku`, `x5u`) are never trusted.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

import httpx
import jwt

from app.auth.errors import AuthUnavailableError, UnknownSigningKeyError
from app.core.clock import Clock
from app.core.logging import get_logger

log = get_logger(__name__)

# Only asymmetric keys: a symmetric entry in a JWKS would let anyone who read it mint tokens.
_ASYMMETRIC_KEY_TYPES = frozenset({"EC", "RSA"})


class JwksCache:
    def __init__(
        self,
        url: str,
        *,
        http: httpx.AsyncClient,
        clock: Clock,
        ttl_seconds: float = 600,
        min_forced_refresh_seconds: float = 30,
        retry_after_failure_seconds: float = 30,
        timeout_seconds: float = 5,
    ) -> None:
        self._url = url
        self._http = http
        self._clock = clock
        self._ttl = timedelta(seconds=ttl_seconds)
        self._min_forced_refresh = timedelta(seconds=min_forced_refresh_seconds)
        self._retry_after_failure = timedelta(seconds=retry_after_failure_seconds)
        self._timeout = timeout_seconds
        self._keys: dict[str, jwt.PyJWK] = {}
        self._next_refresh_at: datetime | None = None
        self._last_forced_refresh_at: datetime | None = None
        self._lock = asyncio.Lock()

    async def get_key(self, kid: str) -> jwt.PyJWK:
        if self._due_for_refresh():
            await self._refresh(forced=False)
        key = self._keys.get(kid)
        if key is None and self._may_force_refresh():
            await self._refresh(forced=True)
            key = self._keys.get(kid)
        if key is None:
            raise UnknownSigningKeyError(kid)
        return key

    def _due_for_refresh(self) -> bool:
        return self._next_refresh_at is None or self._clock.now() >= self._next_refresh_at

    def _may_force_refresh(self) -> bool:
        last = self._last_forced_refresh_at
        return last is None or self._clock.now() - last >= self._min_forced_refresh

    async def _refresh(self, *, forced: bool) -> None:
        async with self._lock:
            # Another request may have refreshed while this one waited for the lock.
            if forced and not self._may_force_refresh():
                return
            if not forced and not self._due_for_refresh():
                return
            now = self._clock.now()
            if forced:
                self._last_forced_refresh_at = now
            try:
                self._keys = await self._fetch()
            except (httpx.HTTPError, ValueError) as exc:
                log.warning("jwks_refresh_failed", error_type=type(exc).__name__, error=str(exc))
                if not self._keys:
                    raise AuthUnavailableError("Signing keys could not be fetched") from exc
                self._next_refresh_at = now + self._retry_after_failure
                return
            self._next_refresh_at = now + self._ttl
            log.info("jwks_refreshed", key_ids=sorted(self._keys), forced=forced)

    async def _fetch(self) -> dict[str, jwt.PyJWK]:
        response = await self._http.get(self._url, timeout=self._timeout)
        response.raise_for_status()
        document: Any = response.json()  # ValueError if the body is not JSON
        entries = document.get("keys") if isinstance(document, dict) else None
        if not isinstance(entries, list):
            raise ValueError("JWKS document has no 'keys' list")
        keys: dict[str, jwt.PyJWK] = {}
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("kty") not in _ASYMMETRIC_KEY_TYPES:
                continue
            try:
                key = jwt.PyJWK(entry)
            except jwt.PyJWTError:
                continue
            if key.key_id:
                keys[key.key_id] = key
        if not keys:
            raise ValueError("JWKS document has no usable asymmetric keys")
        return keys
