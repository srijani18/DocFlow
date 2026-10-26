"""Gemini over the Generative Language REST API (F4 plan §2). Only this module talks to
Google; everything else goes through the gateway (constitution §5.1)."""

import base64
import json
import re
from typing import Any

import httpx

from app.llm.inputs import Capabilities
from app.llm.providers.gemini_schema import adapt_schema
from app.llm.types import (
    CredentialRejectedError,
    FilePart,
    PermanentLlmError,
    ProviderRequest,
    ProviderResponse,
    TextPart,
    TransientLlmError,
)

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com"
_RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}
_DURATION = re.compile(r"^(\d+(?:\.\d+)?)s$")


def _retry_after(body: Any) -> float | None:
    """Seconds from a google.rpc.RetryInfo detail, e.g. {"retryDelay": "37s"}."""
    try:
        details = body["error"]["details"]
    except (KeyError, TypeError):
        return None
    for detail in details:
        if str(detail.get("@type", "")).endswith("google.rpc.RetryInfo"):
            match = _DURATION.match(str(detail.get("retryDelay", "")))
            if match:
                return float(match.group(1))
    return None


def _part(part: TextPart | FilePart) -> dict[str, Any]:
    if isinstance(part, TextPart):
        return {"text": part.text}
    return {
        "inlineData": {"mimeType": part.mime_type, "data": base64.b64encode(part.data).decode()}
    }


class GeminiProvider:
    name = "gemini"
    capabilities = Capabilities(reads_pdf=True, max_images=16)

    def __init__(
        self,
        *,
        http: httpx.AsyncClient,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = 60,
    ) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        body = {
            "systemInstruction": {"parts": [{"text": request.instructions}]},
            "contents": [{"role": "user", "parts": [_part(part) for part in request.parts]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseJsonSchema": adapt_schema(request.response_schema),
            },
        }
        url = f"{self._base_url}/v1beta/models/{request.model}:generateContent"
        try:
            response = await self._http.post(
                url,
                json=body,
                headers={"x-goog-api-key": request.api_key},
                timeout=self._timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise TransientLlmError("Gemini timed out") from exc
        except httpx.HTTPError as exc:
            raise TransientLlmError(f"Gemini unreachable: {type(exc).__name__}") from exc

        payload = _json_or_none(response)
        if response.status_code in _RETRYABLE_STATUSES:
            raise TransientLlmError(
                f"Gemini returned {response.status_code}", retry_after_seconds=_retry_after(payload)
            )
        message = _error_message(payload)
        if response.status_code in (401, 403) or "API_KEY_INVALID" in str(payload):
            # The workspace's own key was refused (F15 AC9). Gemini answers 400
            # API_KEY_INVALID for unknown keys and 403 for keys without access.
            raise CredentialRejectedError(
                f"Gemini rejected the key ({response.status_code})", provider=self.name
            )
        if response.status_code >= 400:
            raise PermanentLlmError(
                f"Gemini rejected the request ({response.status_code}): {message}"
            )
        return _parse(payload)


def _error_message(payload: Any) -> str:
    if isinstance(payload, dict):
        return str(payload.get("error", {}).get("message", ""))
    return ""


def _json_or_none(response: httpx.Response) -> Any:
    try:
        return response.json()
    except (json.JSONDecodeError, ValueError):
        return None


def _parse(payload: Any) -> ProviderResponse:
    if not isinstance(payload, dict):
        # A 200 whose body isn't JSON points at a proxy or network hiccup: try again.
        raise TransientLlmError("Gemini returned a response that isn't JSON")
    try:
        candidate = payload["candidates"][0]
        text = "".join(part.get("text", "") for part in candidate["content"]["parts"])
    except (KeyError, IndexError, TypeError) as exc:
        # No candidate usually means the prompt or file was blocked: retrying won't help.
        reason = (
            (payload or {}).get("promptFeedback", {}).get("blockReason")
            if isinstance(payload, dict)
            else None
        )
        raise PermanentLlmError(f"Gemini returned no answer (block reason: {reason})") from exc
    usage = payload.get("usageMetadata", {})
    output_tokens = usage.get("candidatesTokenCount")
    if output_tokens is not None:
        output_tokens += usage.get("thoughtsTokenCount", 0)  # billed as output
    return ProviderResponse(
        text=text,
        model=payload.get("modelVersion", "unknown"),
        input_tokens=usage.get("promptTokenCount"),
        output_tokens=output_tokens,
        truncated=candidate.get("finishReason") == "MAX_TOKENS",
    )
