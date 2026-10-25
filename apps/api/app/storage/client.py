"""File storage interface (ADR-0004). The API never streams file bytes to browsers: it
hands out signed tokens and URLs, and only the worker downloads bytes."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.core.errors import ServiceUnavailableError


class StorageUnavailableError(ServiceUnavailableError):
    type_slug = "storage-unavailable"
    title = "File storage temporarily unavailable"


@dataclass(frozen=True)
class SignedUpload:
    """What the browser needs to PUT one file straight into the bucket."""

    bucket: str
    path: str
    token: str


@dataclass(frozen=True)
class ObjectInfo:
    size_bytes: int
    content_type: str | None


@dataclass(frozen=True)
class SignedUrl:
    url: str
    expires_at: datetime


class Storage(Protocol):
    @property
    def bucket(self) -> str: ...

    async def create_signed_upload(self, path: str) -> SignedUpload: ...

    async def object_info(self, path: str) -> ObjectInfo | None:
        """Size and type of a stored object, or None if it doesn't exist."""
        ...

    async def create_signed_url(self, path: str, *, ttl_seconds: int) -> SignedUrl: ...

    async def download(self, path: str) -> bytes: ...
