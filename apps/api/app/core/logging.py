"""Structured logging (constitution §6.5 and §10.1).

One JSON event per line in production. Context such as `request_id` is bound with
`structlog.contextvars` and merged into every event. Known sensitive keys are redacted
before rendering, so a careless `log.info(..., email=...)` never leaks.
"""

import logging
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

from app.core.config import Settings

REDACTED = "[REDACTED]"

_SENSITIVE_EXACT = frozenset({"authorization", "cookie", "set-cookie", "email", "password"})
_SENSITIVE_PARTS = ("token", "secret", "password", "api_key", "apikey", "dsn")
# LLM usage counts contain "token" but are numbers we need in logs (constitution §5.2).
_NOT_SENSITIVE = frozenset({"input_tokens", "output_tokens", "total_tokens"})


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    if lowered in _NOT_SENSITIVE:
        return False
    return lowered in _SENSITIVE_EXACT or any(part in lowered for part in _SENSITIVE_PARTS)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: REDACTED if _is_sensitive(str(k)) else _redact(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_redact(item) for item in value]
    return value


def redact_sensitive(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """structlog processor: mask values whose key looks sensitive, at any depth."""
    for key in list(event_dict):
        event_dict[key] = REDACTED if _is_sensitive(key) else _redact(event_dict[key])
    return event_dict


def configure_logging(settings: Settings) -> None:
    level = logging.getLevelNamesMapping()[settings.log_level]
    renderer: structlog.types.Processor = (
        structlog.dev.ConsoleRenderer()
        if settings.environment == "local"
        else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_sensitive,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=False,
    )
    # Libraries using stdlib logging (uvicorn, sqlalchemy) go to stderr at the same level.
    logging.basicConfig(level=level, stream=sys.stderr, force=True)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
