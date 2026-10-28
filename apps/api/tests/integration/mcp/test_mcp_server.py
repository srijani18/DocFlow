"""F12 AC4-AC8: the MCP server, driven by the MCP SDK's own client over the app in process."""

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any

import httpx
import httpx2
import pytest
from fastapi import FastAPI
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ratelimit import RateLimiter
from app.documents.models import Document
from app.storage.fake import FakeStorage
from tests.integration.conftest import FakeQueryEmbedder
from tests.integration.export.test_export_api import approve
from tests.integration.search.test_search_api import INVOICE, indexed
from tests.support.clock import FrozenClock
from tests.support.documents import as_user
from tests.support.identity import TwoWorkspaces, UserRef

TOOLS = {"search_documents", "get_document", "list_vendors", "spend_summary"}


@pytest.fixture(autouse=True)
def mcp_in_test_transaction(
    db_app: FastAPI,
    db_session: AsyncSession,
    clock: FrozenClock,
    query_embedder: FakeQueryEmbedder,
) -> None:
    """The tools and the token check use the test's session, clock and embedder."""

    @asynccontextmanager
    async def test_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    deps = db_app.state.mcp_deps
    deps.open_session = test_session
    deps.clock = clock
    deps.query_embedder = query_embedder


async def new_token(client: httpx.AsyncClient, w: TwoWorkspaces, user: UserRef) -> dict[str, Any]:
    response = await client.post(
        f"/v1/workspaces/{w.a.id}/api-tokens", json={"name": "test"}, headers=as_user(user)
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


@asynccontextmanager
async def connect(app: FastAPI, token: str) -> AsyncIterator[ClientSession]:
    http = httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    )
    async with (
        http,
        streamable_http_client("http://test/mcp", http_client=http) as (read, write, *_),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        yield session


async def call(session: ClientSession, tool: str, **arguments: Any) -> dict[str, Any]:
    result = await session.call_tool(tool, arguments)
    assert not result.is_error, result.content
    text = result.content[0].text  # type: ignore[union-attr]
    body: dict[str, Any] = json.loads(text)
    return body


async def test_ac4_requests_without_a_valid_token_are_refused(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces
) -> None:
    w = two_workspaces
    token = await new_token(db_client, w, w.a_reviewer)
    await db_client.delete(
        f"/v1/workspaces/{w.a.id}/api-tokens/{token['id']}", headers=as_user(w.a_reviewer)
    )
    ping = {"jsonrpc": "2.0", "id": 1, "method": "ping"}

    missing = await db_client.post("/mcp", json=ping)
    revoked = await db_client.post(
        "/mcp", json=ping, headers={"Authorization": f"Bearer {token['token']}"}
    )
    made_up = await db_client.post(
        "/mcp", json=ping, headers={"Authorization": "Bearer dfw_not-a-real-token"}
    )
    metadata = await db_client.get("/.well-known/oauth-protected-resource/mcp")

    assert [missing.status_code, revoked.status_code, made_up.status_code] == [401, 401, 401]
    assert missing.headers["www-authenticate"] == (
        'Bearer resource_metadata="http://test/.well-known/oauth-protected-resource/mcp"'
    )
    assert metadata.json()["resource"] == "http://test/mcp"


async def test_ac4_ac5_lists_four_read_only_tools(
    db_client: httpx.AsyncClient, db_app: FastAPI, two_workspaces: TwoWorkspaces
) -> None:
    token = await new_token(db_client, two_workspaces, two_workspaces.a_reviewer)

    async with connect(db_app, token["token"]) as session:
        tools = (await session.list_tools()).tools

    assert {tool.name for tool in tools} == TOOLS
    for tool in tools:
        assert tool.description
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint
    search = next(tool for tool in tools if tool.name == "search_documents")
    assert search.input_schema["properties"]["limit"]["maximum"] == 20


async def test_ac5_search_then_get_the_approved_document(
    db_client: httpx.AsyncClient,
    db_app: FastAPI,
    db_session: AsyncSession,
    fake_storage: FakeStorage,
    two_workspaces: TwoWorkspaces,
) -> None:
    w = two_workspaces
    invoice = await indexed(
        db_client, fake_storage, db_session, w, doc_type="invoice", data=INVOICE
    )
    await approve(db_session, invoice, by_agent=False)
    token = await new_token(db_client, w, w.a_reviewer)

    async with connect(db_app, token["token"]) as session:
        found = await call(session, "search_documents", query="Kaveri brackets", limit=5)
        document = await call(session, "get_document", document_id=invoice)

    assert [hit["id"] for hit in found["documents"]] == [invoice]
    assert found["documents"][0]["link"] == f"http://localhost:3000/app/documents/{invoice}"
    assert "note" not in found
    assert document["version"] == "approved"
    assert document["approved_by"] == "a reviewer"
    assert document["data"]["invoice_number"] == INVOICE["invoice_number"]
    assert isinstance(document["open_issues"], list)


async def test_ac6_another_workspaces_document_is_not_found(
    db_client: httpx.AsyncClient,
    db_app: FastAPI,
    db_session: AsyncSession,
    fake_storage: FakeStorage,
    two_workspaces: TwoWorkspaces,
) -> None:
    w = two_workspaces
    theirs = await indexed(
        db_client, fake_storage, db_session, w, doc_type="invoice", data=INVOICE, workspace="b"
    )
    token = await new_token(db_client, w, w.a_admin)

    async with connect(db_app, token["token"]) as session:
        other = await session.call_tool("get_document", {"document_id": theirs})
        unknown = await session.call_tool("get_document", {"document_id": str(uuid.uuid4())})
        found = await call(session, "search_documents", query="Kaveri")

    assert other.is_error
    assert unknown.is_error
    assert other.content == unknown.content
    assert found["documents"] == []


async def test_ac5_spend_is_approved_only_and_per_currency(
    db_client: httpx.AsyncClient,
    db_app: FastAPI,
    db_session: AsyncSession,
    fake_storage: FakeStorage,
    two_workspaces: TwoWorkspaces,
) -> None:
    w = two_workspaces
    rows = [
        ("Kaveri Fasteners", "INR", "1180.00", True),
        ("Kaveri Fasteners", "INR", "820.50", True),
        ("Kaveri Fasteners", "USD", "40.00", True),
        ("Annapurna Tiffins", "INR", "250.00", True),
        ("Annapurna Tiffins", "INR", "999.00", False),  # waiting for review
    ]
    for vendor, currency, total, approved in rows:
        document_id = await indexed(
            db_client, fake_storage, db_session, w, doc_type="invoice", data=INVOICE
        )
        await db_session.execute(
            update(Document)
            .where(Document.id == uuid.UUID(document_id))
            .values(vendor_name=vendor, currency=currency, total_amount=Decimal(total))
        )
        if approved:
            await approve(db_session, document_id)
    token = await new_token(db_client, w, w.a_reviewer)

    async with connect(db_app, token["token"]) as session:
        spend = await call(session, "spend_summary", group_by="vendor")
        with_pending = await call(session, "spend_summary", include_unapproved=True, vendor="anna")
        vendors = await call(session, "list_vendors")

    assert spend["groups"] == [
        {"vendor": "Kaveri Fasteners", "currency": "INR", "documents": 2, "total": "2000.50"},
        {"vendor": "Annapurna Tiffins", "currency": "INR", "documents": 1, "total": "250.00"},
        {"vendor": "Kaveri Fasteners", "currency": "USD", "documents": 1, "total": "40.00"},
    ]
    assert with_pending["groups"] == [
        {"vendor": "Annapurna Tiffins", "currency": "INR", "documents": 2, "total": "1249.00"}
    ]
    assert vendors["vendors"][0] == {
        "name": "Kaveri Fasteners",
        "documents": 3,
        "approved_documents": 3,
        "last_document_date": INVOICE["invoice_date"],
        "approved_totals": {"INR": "2000.50", "USD": "40.00"},
    }


async def test_ac7_ac8_logged_without_arguments_and_keyword_only_without_a_key(
    db_client: httpx.AsyncClient,
    db_app: FastAPI,
    query_embedder: FakeQueryEmbedder,
    two_workspaces: TwoWorkspaces,
    capsys: pytest.CaptureFixture[str],
) -> None:
    query_embedder.available = False
    token = await new_token(db_client, two_workspaces, two_workspaces.a_reviewer)

    async with connect(db_app, token["token"]) as session:
        found = await call(session, "search_documents", query="secret-vendor-name")

    logged = capsys.readouterr().out
    assert "keyword matches only" in found["note"]
    assert "mcp_tool_called" in logged
    assert "secret-vendor-name" not in logged


async def test_f14_ac9_mcp_calls_are_limited_per_token(
    db_client: httpx.AsyncClient, db_app: FastAPI, two_workspaces: TwoWorkspaces
) -> None:
    db_app.state.mcp_deps.limiter = RateLimiter({"general": 100, "uploads": 1, "ai": 1, "mcp": 1})
    token = await new_token(db_client, two_workspaces, two_workspaces.a_reviewer)
    headers = {
        "Authorization": f"Bearer {token['token']}",
        "Accept": "application/json, text/event-stream",
    }
    ping = {"jsonrpc": "2.0", "id": 1, "method": "ping"}

    first = await db_client.post("/mcp", json=ping, headers=headers)
    second = await db_client.post("/mcp", json=ping, headers=headers)

    assert first.status_code != 429
    assert second.status_code == 429
    assert second.headers["retry-after"] == "60"
    assert second.json()["type"].endswith("/rate-limited")
