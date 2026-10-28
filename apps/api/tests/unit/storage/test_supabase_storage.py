from collections.abc import AsyncIterator
from datetime import timedelta

import httpx
import pytest
import respx

from app.storage.client import StorageUnavailableError
from app.storage.supabase import SupabaseStorage
from tests.support.clock import FrozenClock

BASE = "https://proj.supabase.co/storage/v1"
PATH = "11111111-1111-1111-1111-111111111111/22222222-2222-2222-2222-222222222222"


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock()


def storage(
    http: httpx.AsyncClient, clock: FrozenClock, key: str | None = "sb_secret_x"
) -> SupabaseStorage:
    return SupabaseStorage(
        supabase_url="https://proj.supabase.co",
        secret_key=key,
        bucket="docs",
        http=http,
        clock=clock,
    )


@respx.mock
async def test_signed_upload_returns_token_and_uses_secret_key(
    http: httpx.AsyncClient, clock: FrozenClock
) -> None:
    route = respx.post(f"{BASE}/object/upload/sign/docs/{PATH}").respond(
        json={"url": f"/object/upload/sign/docs/{PATH}?token=abc.def"}
    )

    ticket = await storage(http, clock).create_signed_upload(PATH)

    assert (ticket.bucket, ticket.path, ticket.token) == ("docs", PATH, "abc.def")
    request = route.calls.last.request
    assert request.headers["apikey"] == "sb_secret_x"
    assert request.headers["authorization"] == "Bearer sb_secret_x"


@respx.mock
async def test_object_info_reads_size_and_type(http: httpx.AsyncClient, clock: FrozenClock) -> None:
    respx.head(f"{BASE}/object/authenticated/docs/{PATH}").respond(
        headers={"content-length": "1234", "content-type": "application/pdf"}
    )

    info = await storage(http, clock).object_info(PATH)

    assert info is not None
    assert (info.size_bytes, info.content_type) == (1234, "application/pdf")


@pytest.mark.parametrize("status", [400, 404])
@respx.mock
async def test_object_info_missing_object_is_none(
    http: httpx.AsyncClient, clock: FrozenClock, status: int
) -> None:
    respx.head(f"{BASE}/object/authenticated/docs/{PATH}").respond(status)

    assert await storage(http, clock).object_info(PATH) is None


@respx.mock
async def test_signed_url_is_absolute_and_expires(
    http: httpx.AsyncClient, clock: FrozenClock
) -> None:
    route = respx.post(f"{BASE}/object/sign/docs/{PATH}").respond(
        json={"signedURL": f"/object/sign/docs/{PATH}?token=view"}
    )

    signed = await storage(http, clock).create_signed_url(PATH, ttl_seconds=300)

    assert signed.url == f"{BASE}/object/sign/docs/{PATH}?token=view"
    assert signed.expires_at == clock.now() + timedelta(seconds=300)
    assert route.calls.last.request.read() == b'{"expiresIn":300}'


@respx.mock
async def test_download_returns_bytes(http: httpx.AsyncClient, clock: FrozenClock) -> None:
    respx.get(f"{BASE}/object/authenticated/docs/{PATH}").respond(content=b"%PDF-1.7")

    assert await storage(http, clock).download(PATH) == b"%PDF-1.7"


@pytest.mark.parametrize("status", [500, 503, 401, 403])
@respx.mock
async def test_server_and_auth_errors_are_unavailable(
    http: httpx.AsyncClient, clock: FrozenClock, status: int
) -> None:
    respx.post(f"{BASE}/object/upload/sign/docs/{PATH}").respond(status)

    with pytest.raises(StorageUnavailableError):
        await storage(http, clock).create_signed_upload(PATH)


@respx.mock
async def test_network_error_is_unavailable(http: httpx.AsyncClient, clock: FrozenClock) -> None:
    respx.get(f"{BASE}/object/authenticated/docs/{PATH}").mock(
        side_effect=httpx.ConnectTimeout("x")
    )

    with pytest.raises(StorageUnavailableError):
        await storage(http, clock).download(PATH)


async def test_missing_secret_key_is_unavailable(
    http: httpx.AsyncClient, clock: FrozenClock
) -> None:
    with pytest.raises(StorageUnavailableError):
        await storage(http, clock, key=None).create_signed_upload(PATH)


@respx.mock
async def test_f14_delete_removes_objects_in_one_request(
    http: httpx.AsyncClient, clock: FrozenClock
) -> None:
    route = respx.delete(f"{BASE}/object/docs").respond(json=[{"name": PATH}])

    await storage(http, clock).delete([PATH, "other/path"])
    await storage(http, clock).delete([])  # nothing to do: no request

    assert route.call_count == 1
    assert route.calls.last.request.read() == (
        b'{"prefixes":["' + PATH.encode() + b'","other/path"]}'
    )
