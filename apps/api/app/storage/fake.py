"""In-memory storage for tests and local runs without a Supabase key."""

from datetime import timedelta

from app.core.clock import Clock, SystemClock
from app.storage.client import ObjectInfo, SignedUpload, SignedUrl


class FakeStorage:
    def __init__(self, *, bucket: str = "documents-test", clock: Clock | None = None) -> None:
        self._bucket = bucket
        self._clock = clock or SystemClock()
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.signed_uploads: list[str] = []

    @property
    def bucket(self) -> str:
        return self._bucket

    def put(self, path: str, data: bytes, content_type: str = "application/pdf") -> None:
        """What the browser's direct upload would do."""
        self.objects[path] = (data, content_type)

    async def create_signed_upload(self, path: str) -> SignedUpload:
        self.signed_uploads.append(path)
        return SignedUpload(bucket=self._bucket, path=path, token=f"token-for-{path}")

    async def object_info(self, path: str) -> ObjectInfo | None:
        if path not in self.objects:
            return None
        data, content_type = self.objects[path]
        return ObjectInfo(size_bytes=len(data), content_type=content_type)

    async def create_signed_url(self, path: str, *, ttl_seconds: int) -> SignedUrl:
        return SignedUrl(
            url=f"https://storage.test/{self._bucket}/{path}?token=view",
            expires_at=self._clock.now() + timedelta(seconds=ttl_seconds),
        )

    async def download(self, path: str) -> bytes:
        return self.objects[path][0]

    async def delete(self, paths: list[str]) -> None:
        for path in paths:
            self.objects.pop(path, None)
