"""Error tracking with Sentry (F16 plan §2, §3).

Errors are reported explicitly, at the three places an unexpected error ends up: the
last-resort 500, a crashed job and the worker loop. Sentry's automatic integrations stay off,
so expected outcomes (4xx answers, retries, a provider being down) are never reported, and
nothing is sent twice.

Every event passes through `scrub_event` first: it carries the stack trace and our ids, never
request bodies, document content, AI keys or email addresses (AC7).
"""

import re
from typing import Any

import sentry_sdk
import structlog

from app.core.config import Settings
from app.core.logging import REDACTED, is_sensitive_key

# Ids that help find the request, document or job; none of them is personal data.
TAG_KEYS = ("request_id", "workspace_id", "document_id", "job_id", "kind")
# Keys whose values are a document's content or a user's search (F8, F9).
_CONTENT_KEYS = frozenset({"data", "text", "snippet", "q", "query_string", "cookies", "body"})
_SECRET_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),  # Google AI
    re.compile(r"gsk_[0-9A-Za-z]{20,}"),  # Groq
    re.compile(r"sk-or-[0-9A-Za-z-]{20,}"),  # OpenRouter
    re.compile(r"sb_secret_[0-9A-Za-z_-]{10,}"),  # Supabase
    re.compile(r"Bearer\s+[0-9A-Za-z._~+/=-]+", re.IGNORECASE),
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),  # email addresses
)

log = structlog.get_logger(__name__)


def init_sentry(settings: Settings, *, transport: Any = None) -> bool:
    """Start error reporting if SENTRY_DSN is set (AC8). Returns whether it is on.
    `transport` replaces sending, for tests."""
    if not settings.sentry_dsn:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment or settings.environment,
        release=settings.render_git_commit,
        default_integrations=False,
        auto_enabling_integrations=False,
        traces_sample_rate=0,  # errors only (spec D1)
        include_local_variables=False,  # frame locals can hold document data
        # No send_default_pii (off by default) and no data_collection: Sentry then also runs
        # its own EventScrubber, behind ours.
        max_request_body_size="never",
        before_send=scrub_event,
        before_breadcrumb=lambda crumb, _hint: scrub(crumb),
        transport=transport,
    )
    log.info("sentry_enabled", environment=settings.sentry_environment or settings.environment)
    return True


def report_exception(error: BaseException, **tags: object) -> None:
    """Send an unexpected error with the ids bound to this request or job. A no-op when
    Sentry is off."""
    bound = structlog.contextvars.get_contextvars()
    with sentry_sdk.new_scope() as scope:
        for key in TAG_KEYS:
            value = tags.get(key, bound.get(key))
            if value is not None:
                scope.set_tag(key, str(value))
        sentry_sdk.capture_exception(error)


def scrub_event(event: Any, _hint: Any) -> Any:
    return scrub(event)


def scrub(value: Any, key: str = "") -> Any:
    """Redact sensitive or content-bearing values at any depth, and secrets inside strings."""
    if key and (is_sensitive_key(key) or key.lower() in _CONTENT_KEYS):
        return REDACTED
    if isinstance(value, dict):
        return {k: scrub(v, str(k)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [scrub(item) for item in value]
    if isinstance(value, str):
        for pattern in _SECRET_PATTERNS:
            value = pattern.sub(REDACTED, value)
    return value


def send_check(settings: Settings) -> bool:
    """Send one test error, to confirm the DSN and the scrubbing (deploy guide §7)."""
    if not init_sentry(settings):
        return False
    try:
        raise RuntimeError("DocFlow Sentry check for check@example.com")  # email is scrubbed
    except RuntimeError as exc:
        report_exception(exc, request_id="sentry-check")
    sentry_sdk.flush(timeout=10)
    return True


if __name__ == "__main__":
    from app.core.config import load_settings

    sent = send_check(load_settings())
    print("Sent a test error to Sentry." if sent else "SENTRY_DSN is not set.")
    raise SystemExit(0 if sent else 1)
