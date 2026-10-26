import json
from collections.abc import AsyncIterator

import httpx
import pytest
import respx

from app.llm.providers.openai_compat import describe_schema, groq, openrouter
from app.llm.types import (
    CredentialRejectedError,
    FilePart,
    PermanentLlmError,
    ProviderRequest,
    TextPart,
    TransientLlmError,
)

GROQ = "https://api.groq.com/openai/v1/chat/completions"
OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
REQUEST = ProviderRequest(
    model="meta-llama/llama-4-scout-17b-16e-instruct",
    instructions="Classify this.",
    parts=[TextPart("hello"), FilePart("image/png", b"PNGDATA")],
    response_schema={
        "type": "object",
        "x-schema-id": "x",
        "properties": {"pattern": {"type": "string", "x-eval": "exact"}},
    },
    api_key="workspace-key",
)


def ok(content: str, finish: str = "stop") -> dict[str, object]:
    return {
        "model": "meta-llama/llama-4-scout-17b-16e-instruct",
        "choices": [{"message": {"content": content}, "finish_reason": finish}],
        "usage": {"prompt_tokens": 900, "completion_tokens": 40},
    }


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


@respx.mock
async def test_groq_request_shape_and_answer(http: httpx.AsyncClient) -> None:
    route = respx.post(GROQ).respond(json=ok('{"doc_type": "invoice"}'))

    response = await groq(http, timeout_seconds=30).generate(REQUEST)

    assert (response.text, response.input_tokens, response.output_tokens) == (
        '{"doc_type": "invoice"}',
        900,
        40,
    )
    sent = route.calls.last.request
    assert sent.headers["authorization"] == "Bearer workspace-key"
    body = json.loads(sent.content)
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"][1]["content"][1] == {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,UE5HREFUQQ=="},
    }
    system = body["messages"][0]["content"]
    assert "x-eval" not in system
    assert '"pattern": {"type": "string"}' in system


@respx.mock
async def test_openrouter_has_no_json_mode_and_strips_code_fences(http: httpx.AsyncClient) -> None:
    route = respx.post(OPENROUTER).respond(json=ok('```json\n{"doc_type": "receipt"}\n```'))

    response = await openrouter(http, timeout_seconds=30).generate(REQUEST)

    assert response.text == '{"doc_type": "receipt"}'
    assert "response_format" not in json.loads(route.calls.last.request.content)


@respx.mock
async def test_rate_limit_is_transient_with_retry_after(http: httpx.AsyncClient) -> None:
    respx.post(GROQ).respond(
        429, headers={"retry-after": "12"}, json={"error": {"message": "rate"}}
    )

    with pytest.raises(TransientLlmError) as raised:
        await groq(http, timeout_seconds=30).generate(REQUEST)
    assert raised.value.retry_after_seconds == 12


@pytest.mark.parametrize("status", [401, 403])
@respx.mock
async def test_rejected_key(http: httpx.AsyncClient, status: int) -> None:
    respx.post(GROQ).respond(status, json={"error": {"message": "Invalid API Key"}})

    with pytest.raises(CredentialRejectedError):
        await groq(http, timeout_seconds=30).generate(REQUEST)


@pytest.mark.parametrize(
    ("status", "error"),
    [(503, TransientLlmError), (400, PermanentLlmError), (404, PermanentLlmError)],
)
@respx.mock
async def test_status_mapping(http: httpx.AsyncClient, status: int, error: type[Exception]) -> None:
    respx.post(OPENROUTER).respond(status, json={"error": {"message": "x"}})

    with pytest.raises(error):
        await openrouter(http, timeout_seconds=30).generate(REQUEST)


@respx.mock
async def test_timeout_and_garbage_are_transient(http: httpx.AsyncClient) -> None:
    respx.post(GROQ).mock(
        side_effect=[httpx.ReadTimeout("slow"), httpx.Response(200, text="<html>")]
    )

    for _ in range(2):
        with pytest.raises(TransientLlmError):
            await groq(http, timeout_seconds=30).generate(REQUEST)


@respx.mock
async def test_length_finish_marks_truncated(http: httpx.AsyncClient) -> None:
    respx.post(GROQ).respond(json=ok('{"doc_type": "inv', finish="length"))

    assert (await groq(http, timeout_seconds=30).generate(REQUEST)).truncated is True


def test_describe_schema_keeps_fields_named_like_annotations() -> None:
    assert describe_schema({"properties": {"examples": {"type": "string", "examples": ["x"]}}}) == {
        "properties": {"examples": {"type": "string"}}
    }
