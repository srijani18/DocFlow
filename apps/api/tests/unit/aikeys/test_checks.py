from collections.abc import AsyncIterator

import httpx
import pytest
import respx

from app.aikeys.checks import CheckResult, check_key

GEMINI = "https://gemini.test/v1beta/models"
GROQ = "https://api.groq.com/openai/v1/models"
OPENROUTER = "https://openrouter.ai/api/v1/key"


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


async def check(provider: str, http: httpx.AsyncClient) -> CheckResult:
    return await check_key(provider, "the-key", http=http, gemini_base_url="https://gemini.test")


@pytest.mark.parametrize(
    ("provider", "url", "header", "value"),
    [
        ("gemini", GEMINI, "x-goog-api-key", "the-key"),
        ("groq", GROQ, "authorization", "Bearer the-key"),
        ("openrouter", OPENROUTER, "authorization", "Bearer the-key"),
    ],
)
@respx.mock
async def test_ac1_valid_key_is_ok_and_sent_only_to_its_provider(
    http: httpx.AsyncClient, provider: str, url: str, header: str, value: str
) -> None:
    route = respx.get(url__startswith=url).respond(json={"data": []})

    assert await check(provider, http) is CheckResult.OK
    assert route.calls.last.request.headers[header] == value
    assert len(respx.calls) == 1


@pytest.mark.parametrize("status", [400, 401, 403])
@respx.mock
async def test_ac1_rejected_key(http: httpx.AsyncClient, status: int) -> None:
    respx.get(url__startswith=GROQ).respond(status, json={"error": {"message": "Invalid API Key"}})

    assert await check("groq", http) is CheckResult.REJECTED


@respx.mock
async def test_rate_limited_key_counts_as_valid(http: httpx.AsyncClient) -> None:
    respx.get(url__startswith=GEMINI).respond(429)

    assert await check("gemini", http) is CheckResult.OK


@pytest.mark.parametrize("failure", [httpx.ConnectTimeout("x"), httpx.ConnectError("x")])
@respx.mock
async def test_provider_down_is_unavailable(http: httpx.AsyncClient, failure: Exception) -> None:
    respx.get(url__startswith=OPENROUTER).mock(side_effect=failure)

    assert await check("openrouter", http) is CheckResult.UNAVAILABLE


@respx.mock
async def test_server_error_is_unavailable(http: httpx.AsyncClient) -> None:
    respx.get(url__startswith=GROQ).respond(503)

    assert await check("groq", http) is CheckResult.UNAVAILABLE
