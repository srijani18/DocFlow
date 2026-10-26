"""Is this key valid for this provider? (F15 AC1, AC5)

Each check is one cheap authenticated request that sends no document data:
- Gemini:     GET  {gemini}/v1beta/models?pageSize=1        (x-goog-api-key)
- Groq:       GET  https://api.groq.com/openai/v1/models    (Bearer)
- OpenRouter: GET  https://openrouter.ai/api/v1/key         (Bearer; /models is public, /key isn't)
"""

from enum import StrEnum

import httpx

from app.core.logging import get_logger

log = get_logger(__name__)

CHECK_TIMEOUT_SECONDS = 10
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class CheckResult(StrEnum):
    OK = "ok"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"  # the provider couldn't answer; say nothing about the key


def _request(provider: str, key: str, gemini_base_url: str) -> tuple[str, dict[str, str]]:
    if provider == "gemini":
        return f"{gemini_base_url.rstrip('/')}/v1beta/models?pageSize=1", {"x-goog-api-key": key}
    if provider == "groq":
        return f"{GROQ_BASE_URL}/models", {"Authorization": f"Bearer {key}"}
    if provider == "openrouter":
        return f"{OPENROUTER_BASE_URL}/key", {"Authorization": f"Bearer {key}"}
    raise ValueError(f"unknown provider {provider!r}")


async def check_key(
    provider: str, key: str, *, http: httpx.AsyncClient, gemini_base_url: str
) -> CheckResult:
    url, headers = _request(provider, key, gemini_base_url)
    try:
        response = await http.get(url, headers=headers, timeout=CHECK_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        log.warning("ai_key_check_unavailable", provider=provider, error_type=type(exc).__name__)
        return CheckResult.UNAVAILABLE
    if response.status_code in (200, 429):
        # 429: the key was accepted but is out of quota right now. That's a quota
        # problem, handled by retries and fallback, not a bad key.
        return CheckResult.OK
    if response.status_code in (400, 401, 403):
        # Gemini answers 400 API_KEY_INVALID for a malformed or unknown key.
        return CheckResult.REJECTED
    log.warning("ai_key_check_unavailable", provider=provider, status=response.status_code)
    return CheckResult.UNAVAILABLE
