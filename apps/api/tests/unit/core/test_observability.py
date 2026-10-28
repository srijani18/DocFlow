import json
from typing import Any

import httpx
import sentry_sdk
from fastapi import FastAPI

from app.core.errors import NotFoundError
from app.core.observability import init_sentry, report_exception, scrub_event, send_check
from tests.conftest import asgi_client, make_settings

# Shaped like real keys, built so secret scanners see no secret.
GOOGLE_KEY = "AIza" + "x" * 35
GROQ_KEY = "gsk_" + "y" * 32
EMAIL = "ada@example.com"
AMOUNT = "118000.50"


def test_ac7_scrubber_removes_keys_emails_and_document_content() -> None:
    event: dict[str, Any] = {
        "message": f"provider rejected {GOOGLE_KEY} for {EMAIL}",
        "request": {
            "url": "https://api.docflow.test/v1/workspaces/w/search",
            "query_string": "q=acme+invoices",
            "headers": {"Authorization": "Bearer eyJhbGciOi.secret", "X-Request-ID": "req-1"},
            "cookies": {"sb-access-token": "secret"},
            "data": {"total_amount": AMOUNT},
        },
        "user": {"id": "user-1", "email": EMAIL},
        "extra": {"api_key": GROQ_KEY, "data": {"totals": {"total": AMOUNT}}, "count": 3},
        "breadcrumbs": {"values": [{"message": "saved", "data": {"text": f"Total {AMOUNT}"}}]},
        "exception": {
            "values": [
                {
                    "type": "ValueError",
                    "value": f"bad key {GROQ_KEY}",
                    "stacktrace": {"frames": [{"function": "extract", "lineno": 42}]},
                }
            ]
        },
        "tags": {"workspace_id": "w-1", "request_id": "req-1"},
    }

    scrubbed = scrub_event(event, {})
    text = json.dumps(scrubbed)

    for secret in (GOOGLE_KEY, GROQ_KEY, EMAIL, AMOUNT, "acme", "eyJhbGciOi"):
        assert secret not in text
    # What's needed to debug stays.
    assert scrubbed["exception"]["values"][0]["stacktrace"]["frames"][0]["function"] == "extract"
    assert scrubbed["tags"] == {"workspace_id": "w-1", "request_id": "req-1"}
    assert scrubbed["request"]["headers"]["X-Request-ID"] == "req-1"
    assert scrubbed["extra"]["count"] == 3


def test_ac8_off_without_a_dsn() -> None:
    assert init_sentry(make_settings()) is False
    assert send_check(make_settings()) is False
    assert not sentry_sdk.get_client().is_active()


def test_ac1_report_carries_release_environment_and_ids(
    sentry_events: list[dict[str, Any]],
) -> None:
    try:
        raise RuntimeError(f"failed for {EMAIL}")
    except RuntimeError as exc:
        report_exception(exc, workspace_id="w-1", document_id="d-1", job_id="j-1", other="x")

    [event] = sentry_events
    assert event["environment"] == "test"
    assert event["tags"] == {"workspace_id": "w-1", "document_id": "d-1", "job_id": "j-1"}
    assert event["exception"]["values"][0]["type"] == "RuntimeError"
    assert EMAIL not in json.dumps(event)


async def test_ac1_ac3_unhandled_500_is_reported_once_and_a_404_never(
    app: FastAPI, sentry_events: list[dict[str, Any]]
) -> None:
    @app.get("/_test/boom")
    async def boom() -> None:
        raise RuntimeError("bug")

    @app.get("/_test/missing")
    async def missing() -> None:
        raise NotFoundError()

    async with await asgi_client(app) as client:
        crashed = await client.get("/_test/boom", headers={"X-Request-ID": "req-500"})
        await client.get("/_test/missing")
        await client.get("/does-not-exist")
        await client.post("/v1/workspaces/x/uploads", json={})  # 401

    assert crashed.status_code == 500
    [event] = sentry_events
    assert event["tags"]["request_id"] == "req-500"
    assert event["exception"]["values"][0]["value"] == "bug"


async def test_ac8_app_runs_without_observability_settings(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz")

    assert response.status_code == 200
    assert not sentry_sdk.get_client().is_active()
