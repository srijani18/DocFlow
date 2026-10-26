import base64
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import respx

from app.llm.providers.gemini import GeminiProvider
from app.llm.types import (
    CredentialRejectedError,
    FilePart,
    PermanentLlmError,
    ProviderRequest,
    TextPart,
    TransientLlmError,
)

URL = "https://gemini.test/v1beta/models/gemini-flash-lite-latest:generateContent"
REQUEST = ProviderRequest(
    model="gemini-flash-lite-latest",
    instructions="Classify this.",
    parts=[TextPart("hello"), FilePart("application/pdf", b"%PDF-1.7")],
    response_schema={
        "type": "object",
        "properties": {"doc_type": {"enum": ["invoice"], "x-eval": "exact"}},
        "required": ["doc_type"],
    },
    api_key="test-key",
)
OK: dict[str, Any] = {
    "candidates": [
        {"content": {"parts": [{"text": '{"doc_type": "invoice"}'}]}, "finishReason": "STOP"}
    ],
    "usageMetadata": {
        "promptTokenCount": 1200,
        "candidatesTokenCount": 20,
        "thoughtsTokenCount": 30,
    },
    "modelVersion": "gemini-3.1-flash-lite-preview",
}


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


def provider(http: httpx.AsyncClient) -> GeminiProvider:
    return GeminiProvider(http=http, base_url="https://gemini.test")


@respx.mock
async def test_success_parses_answer_model_and_tokens(http: httpx.AsyncClient) -> None:
    route = respx.post(URL).respond(json=OK)

    response = await provider(http).generate(REQUEST)

    assert response.text == '{"doc_type": "invoice"}'
    assert response.model == "gemini-3.1-flash-lite-preview"
    assert (response.input_tokens, response.output_tokens) == (
        1200,
        50,
    )  # thinking billed as output
    assert response.truncated is False
    sent = route.calls.last.request
    assert sent.headers["x-goog-api-key"] == "test-key"
    body = json.loads(sent.content)
    assert body["systemInstruction"] == {"parts": [{"text": "Classify this."}]}
    assert body["contents"][0]["parts"] == [
        {"text": "hello"},
        {
            "inlineData": {
                "mimeType": "application/pdf",
                "data": base64.b64encode(b"%PDF-1.7").decode(),
            }
        },
    ]
    config = body["generationConfig"]
    assert (config["temperature"], config["responseMimeType"]) == (0, "application/json")
    assert config["responseJsonSchema"] == {
        "type": "object",
        "properties": {"doc_type": {"enum": ["invoice"]}},
        "required": ["doc_type"],
    }


@respx.mock
async def test_ac5_rate_limit_is_transient_with_retry_after(http: httpx.AsyncClient) -> None:
    respx.post(URL).respond(
        429,
        json={
            "error": {
                "code": 429,
                "status": "RESOURCE_EXHAUSTED",
                "details": [
                    {"@type": "type.googleapis.com/google.rpc.QuotaFailure"},
                    {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "37s"},
                ],
            }
        },
    )

    with pytest.raises(TransientLlmError) as raised:
        await provider(http).generate(REQUEST)

    assert raised.value.retry_after_seconds == 37


@pytest.mark.parametrize("status", [500, 503, 504])
@respx.mock
async def test_ac5_server_errors_are_transient(http: httpx.AsyncClient, status: int) -> None:
    respx.post(URL).respond(status, text="oops")

    with pytest.raises(TransientLlmError) as raised:
        await provider(http).generate(REQUEST)
    assert raised.value.retry_after_seconds is None


@respx.mock
async def test_ac5_timeout_is_transient(http: httpx.AsyncClient) -> None:
    respx.post(URL).mock(side_effect=httpx.ReadTimeout("slow"))

    with pytest.raises(TransientLlmError, match="timed out"):
        await provider(http).generate(REQUEST)


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (
            400,
            {"error": {"status": "INVALID_ARGUMENT", "details": [{"reason": "API_KEY_INVALID"}]}},
        ),
        (401, {"error": {"message": "unauthenticated"}}),
        (403, {"error": {"message": "permission denied"}}),
    ],
)
@respx.mock
async def test_ac9_rejected_key_is_a_credential_error(
    http: httpx.AsyncClient, status: int, body: dict[str, Any]
) -> None:
    respx.post(URL).respond(status, json=body)

    with pytest.raises(CredentialRejectedError) as raised:
        await provider(http).generate(REQUEST)

    assert raised.value.provider == "gemini"
    assert "test-key" not in str(raised.value)


def test_api_key_never_in_request_repr() -> None:
    assert "test-key" not in repr(REQUEST)


@respx.mock
async def test_bad_request_is_permanent(http: httpx.AsyncClient) -> None:
    respx.post(URL).respond(400, json={"error": {"message": "Unable to process input file"}})

    with pytest.raises(PermanentLlmError, match="Unable to process input file"):
        await provider(http).generate(REQUEST)


@respx.mock
async def test_non_json_success_is_transient(http: httpx.AsyncClient) -> None:
    respx.post(URL).respond(200, text="<html>proxy error</html>")

    with pytest.raises(TransientLlmError):
        await provider(http).generate(REQUEST)


@respx.mock
async def test_blocked_prompt_is_permanent(http: httpx.AsyncClient) -> None:
    respx.post(URL).respond(json={"promptFeedback": {"blockReason": "OTHER"}})

    with pytest.raises(PermanentLlmError, match="OTHER"):
        await provider(http).generate(REQUEST)


@respx.mock
async def test_max_tokens_marks_truncated(http: httpx.AsyncClient) -> None:
    respx.post(URL).respond(
        json={**OK, "candidates": [{**OK["candidates"][0], "finishReason": "MAX_TOKENS"}]}
    )

    assert (await provider(http).generate(REQUEST)).truncated is True
