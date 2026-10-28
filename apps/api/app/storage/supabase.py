"""Supabase Storage over its REST API, authenticated with the project's secret key.

Endpoints (Supabase Storage API):
- POST /object/upload/sign/{bucket}/{path}   signed upload token (valid 2 hours)
- HEAD /object/authenticated/{bucket}/{path}  size and type
- POST /object/sign/{bucket}/{path}           signed download URL
- GET  /object/authenticated/{bucket}/{path}  bytes (worker only)
"""

from datetime import timedelta
from urllib.parse import parse_qs, quote, urlsplit

import httpx

from app.core.clock import Clock
from app.core.logging import get_logger
from app.storage.client import ObjectInfo, SignedUpload, SignedUrl, StorageUnavailableError

log = get_logger(__name__)

METADATA_TIMEOUT_SECONDS = 10
DOWNLOAD_TIMEOUT_SECONDS = 30


class SupabaseStorage:
    def __init__(
        self,
        *,
        supabase_url: str,
        secret_key: str | None,
        bucket: str,
        http: httpx.AsyncClient,
        clock: Clock,
    ) -> None:
        self._base = f"{supabase_url}/storage/v1"
        self._secret_key = secret_key
        self._bucket = bucket
        self._http = http
        self._clock = clock

    @property
    def bucket(self) -> str:
        return self._bucket

    def _object_url(self, kind: str, path: str) -> str:
        return f"{self._base}/object/{kind}/{quote(self._bucket)}/{quote(path)}"

    async def _request(
        self,
        method: str,
        url: str,
        *,
        timeout_seconds: float = METADATA_TIMEOUT_SECONDS,
        **kwargs: object,
    ) -> httpx.Response:
        if not self._secret_key:
            log.error("storage_not_configured")
            raise StorageUnavailableError("File storage is not configured.")
        headers = {"apikey": self._secret_key, "Authorization": f"Bearer {self._secret_key}"}
        try:
            response = await self._http.request(
                method,
                url,
                headers=headers,
                timeout=timeout_seconds,
                **kwargs,  # type: ignore[arg-type]
            )
        except httpx.HTTPError as exc:
            log.warning("storage_request_failed", error_type=type(exc).__name__)
            raise StorageUnavailableError() from exc
        if response.status_code >= 500 or response.status_code in (401, 403):
            # 401/403 means our key or bucket setup is wrong: an operator problem, not the user's.
            log.warning("storage_bad_status", status=response.status_code)
            raise StorageUnavailableError()
        return response

    async def create_signed_upload(self, path: str) -> SignedUpload:
        response = await self._request("POST", self._object_url("upload/sign", path))
        response.raise_for_status()
        # {"url": "/object/upload/sign/<bucket>/<path>?token=<token>"}
        token = parse_qs(urlsplit(response.json()["url"]).query)["token"][0]
        return SignedUpload(bucket=self._bucket, path=path, token=token)

    async def object_info(self, path: str) -> ObjectInfo | None:
        response = await self._request("HEAD", self._object_url("authenticated", path))
        if response.status_code in (400, 404):  # Storage answers 400 for some missing objects
            return None
        response.raise_for_status()
        return ObjectInfo(
            size_bytes=int(response.headers["content-length"]),
            content_type=response.headers.get("content-type"),
        )

    async def create_signed_url(self, path: str, *, ttl_seconds: int) -> SignedUrl:
        expires_at = self._clock.now() + timedelta(seconds=ttl_seconds)
        response = await self._request(
            "POST", self._object_url("sign", path), json={"expiresIn": ttl_seconds}
        )
        response.raise_for_status()
        # {"signedURL": "/object/sign/<bucket>/<path>?token=<token>"}
        return SignedUrl(url=self._base + response.json()["signedURL"], expires_at=expires_at)

    async def download(self, path: str) -> bytes:
        response = await self._request(
            "GET", self._object_url("authenticated", path), timeout_seconds=DOWNLOAD_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        return response.content

    async def delete(self, paths: list[str]) -> None:
        if not paths:
            return
        # Bulk delete: missing objects are simply not in the (ignored) answer.
        response = await self._request(
            "DELETE", f"{self._base}/object/{quote(self._bucket)}", json={"prefixes": paths}
        )
        response.raise_for_status()
