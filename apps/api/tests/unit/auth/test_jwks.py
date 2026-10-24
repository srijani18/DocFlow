import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest
import respx

from app.auth.errors import AuthUnavailableError, UnknownSigningKeyError
from app.auth.jwks import JwksCache
from tests.support.clock import FrozenClock
from tests.support.jwt import TEST_JWKS_URL, jwks_document, make_es256_key, make_rs256_key

K1 = make_es256_key("k1")
K2 = make_rs256_key("k2")


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock()


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


@pytest.fixture
def cache(http: httpx.AsyncClient, clock: FrozenClock) -> JwksCache:
    return JwksCache(TEST_JWKS_URL, http=http, clock=clock)


@respx.mock
async def test_ac12_new_kid_triggers_refresh_and_verifies(cache: JwksCache) -> None:
    route = respx.get(TEST_JWKS_URL).respond(json=jwks_document(K1))
    assert (await cache.get_key("k1")).key_id == "k1"

    route.respond(json=jwks_document(K1, K2))  # the provider starts signing with k2
    key = await cache.get_key("k2")

    assert key.key_id == "k2"
    assert route.call_count == 2


@respx.mock
async def test_ac12_removed_key_rejected_after_ttl(cache: JwksCache, clock: FrozenClock) -> None:
    route = respx.get(TEST_JWKS_URL).respond(json=jwks_document(K1))
    await cache.get_key("k1")

    route.respond(json=jwks_document(K2))  # k1 withdrawn
    clock.advance(seconds=599)
    assert (await cache.get_key("k1")).key_id == "k1"  # still inside the cache TTL

    clock.advance(seconds=2)
    with pytest.raises(UnknownSigningKeyError):
        await cache.get_key("k1")


@respx.mock
async def test_ac13_stale_keys_used_when_endpoint_down(
    cache: JwksCache, clock: FrozenClock
) -> None:
    route = respx.get(TEST_JWKS_URL).respond(json=jwks_document(K1))
    await cache.get_key("k1")

    route.side_effect = httpx.ConnectError("provider down")
    clock.advance(minutes=30)

    assert (await cache.get_key("k1")).key_id == "k1"


@respx.mock
@pytest.mark.parametrize(
    "failure",
    [
        httpx.ConnectError("down"),
        httpx.ReadTimeout("slow"),
        httpx.Response(503),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"keys": []}),
    ],
)
async def test_ac13_no_keys_and_endpoint_down_raises_unavailable(
    cache: JwksCache, failure: Exception | httpx.Response
) -> None:
    route = respx.get(TEST_JWKS_URL)
    if isinstance(failure, httpx.Response):
        route.mock(return_value=failure)
    else:
        route.mock(side_effect=failure)

    with pytest.raises(AuthUnavailableError):
        await cache.get_key("k1")


@respx.mock
async def test_unknown_kid_refresh_is_throttled(cache: JwksCache, clock: FrozenClock) -> None:
    route = respx.get(TEST_JWKS_URL).respond(json=jwks_document(K1))
    await cache.get_key("k1")

    with pytest.raises(UnknownSigningKeyError):
        await cache.get_key("random-1")  # forced refresh
    with pytest.raises(UnknownSigningKeyError):
        await cache.get_key("random-2")  # throttled: no request
    assert route.call_count == 2

    clock.advance(seconds=31)
    with pytest.raises(UnknownSigningKeyError):
        await cache.get_key("random-3")
    assert route.call_count == 3


@respx.mock
async def test_concurrent_first_requests_share_one_fetch(cache: JwksCache) -> None:
    route = respx.get(TEST_JWKS_URL).respond(json=jwks_document(K1))

    keys = await asyncio.gather(*(cache.get_key("k1") for _ in range(5)))

    assert {key.key_id for key in keys} == {"k1"}
    assert route.call_count == 1


@respx.mock
async def test_unusable_entries_are_skipped(cache: JwksCache) -> None:
    respx.get(TEST_JWKS_URL).respond(
        json={"keys": [{"kty": "oct", "k": "c2VjcmV0", "kid": "hs"}, K1.public_jwk]}
    )

    assert (await cache.get_key("k1")).key_id == "k1"
    with pytest.raises(UnknownSigningKeyError):
        await cache.get_key("hs")  # symmetric keys are never trusted


@respx.mock
async def test_failed_refresh_backs_off_instead_of_retrying_every_request(
    cache: JwksCache, clock: FrozenClock
) -> None:
    route = respx.get(TEST_JWKS_URL).respond(json=jwks_document(K1))
    await cache.get_key("k1")
    route.side_effect = httpx.ConnectError("provider down")
    clock.advance(minutes=11)

    for _ in range(3):
        await cache.get_key("k1")  # one failed refresh, then served from cache
    assert route.call_count == 2

    clock.advance(seconds=31)
    await cache.get_key("k1")
    assert route.call_count == 3
