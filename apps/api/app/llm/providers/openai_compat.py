"""Groq and OpenRouter speak the OpenAI Chat Completions format (F10 plan §2).

Neither reads PDFs, so the gateway sends page images (`app.llm.inputs`). The schema goes into
the instructions; Groq additionally gets JSON mode. Our own validation decides what counts.
"""

import base64
import json
import re
from typing import Any

import httpx

from app.llm.inputs import Capabilities
from app.llm.types import (
    CredentialRejectedError,
    FilePart,
    PermanentLlmError,
    ProviderRequest,
    ProviderResponse,
    TextPart,
    TransientLlmError,
)

_RETRYABLE = {408, 409, 429, 500, 502, 503, 504}
_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.S)
_ANNOTATIONS = {"$comment", "examples", "$id", "$schema"}


def describe_schema(schema: Any) -> Any:
    """The schema for the instructions, without our own x-* keys or annotations."""
    if isinstance(schema, list):
        return [describe_schema(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    return {
        key: (
            {name: describe_schema(sub) for name, sub in value.items()}
            if key == "properties"
            else describe_schema(value)
        )
        for key, value in schema.items()
        if not key.startswith("x-") and key not in _ANNOTATIONS
    }


def _content(part: TextPart | FilePart) -> dict[str, Any]:
    if isinstance(part, TextPart):
        return {"type": "text", "text": part.text}
    data = base64.b64encode(part.data).decode()
    return {"type": "image_url", "image_url": {"url": f"data:{part.mime_type};base64,{data}"}}


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        http: httpx.AsyncClient,
        capabilities: Capabilities,
        json_mode: bool,
        timeout_seconds: float = 60,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.name = name
        self.capabilities = capabilities
        self._base_url = base_url.rstrip("/")
        self._http = http
        self._json_mode = json_mode
        self._timeout_seconds = timeout_seconds
        self._extra_headers = extra_headers or {}

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        schema = json.dumps(describe_schema(request.response_schema))
        instructions = (
            f"{request.instructions}\n\nRespond with only a JSON object (no prose, no code "
            f"fences) that matches this JSON Schema:\n{schema}"
        )
        body: dict[str, Any] = {
            "model": request.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": [_content(part) for part in request.parts]},
            ],
        }
        if self._json_mode:
            body["response_format"] = {"type": "json_object"}
        try:
            response = await self._http.post(
                f"{self._base_url}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {request.api_key}", **self._extra_headers},
                timeout=self._timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise TransientLlmError(f"{self.name} timed out") from exc
        except httpx.HTTPError as exc:
            raise TransientLlmError(f"{self.name} unreachable: {type(exc).__name__}") from exc

        if response.status_code in (401, 403):
            raise CredentialRejectedError(
                f"{self.name} rejected the key ({response.status_code})", provider=self.name
            )
        if response.status_code in _RETRYABLE:
            raise TransientLlmError(
                f"{self.name} returned {response.status_code}",
                retry_after_seconds=_retry_after(response),
            )
        if response.status_code >= 400:
            raise PermanentLlmError(f"{self.name} rejected the request ({response.status_code})")
        return self._parse(response)

    def _parse(self, response: httpx.Response) -> ProviderResponse:
        try:
            payload = response.json()
            choice = payload["choices"][0]
            text = choice["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise TransientLlmError(f"{self.name} returned an unexpected body") from exc
        fenced = _FENCE.match(text)
        usage = payload.get("usage") or {}
        return ProviderResponse(
            text=fenced.group(1) if fenced else text,
            model=str(payload.get("model") or "unknown"),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            truncated=choice.get("finish_reason") == "length",
        )


GROQ_BASE_URL = "https://api.groq.com/openai/v1"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def groq(http: httpx.AsyncClient, *, timeout_seconds: float) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        name="groq",
        base_url=GROQ_BASE_URL,
        http=http,
        capabilities=Capabilities(reads_pdf=False, max_images=5),
        json_mode=True,
        timeout_seconds=timeout_seconds,
    )


def openrouter(http: httpx.AsyncClient, *, timeout_seconds: float) -> OpenAICompatibleProvider:
    # The free router picks the model, so JSON mode may not be supported: instructions only.
    return OpenAICompatibleProvider(
        name="openrouter",
        base_url=OPENROUTER_BASE_URL,
        http=http,
        capabilities=Capabilities(reads_pdf=False, max_images=3),
        json_mode=False,
        timeout_seconds=timeout_seconds,
        extra_headers={"X-Title": "DocFlow"},
    )
