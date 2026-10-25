"""Helpers for driving the upload flow through the API in tests."""

import hashlib
import uuid
from typing import Any

import httpx

from app.storage.fake import FakeStorage
from tests.support.identity import UserRef
from tests.support.jwt import bearer

PDF = b"%PDF-1.7\n% synthetic test document\n"


def as_user(user: UserRef) -> dict[str, str]:
    return bearer(sub=user.auth_subject, email=user.email)


def upload_body(data: bytes = PDF, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "filename": "invoice.pdf",
        "content_type": "application/pdf",
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    return body | overrides


async def start(
    client: httpx.AsyncClient,
    workspace_id: uuid.UUID,
    user: UserRef,
    data: bytes = PDF,
    **overrides: Any,
) -> httpx.Response:
    return await client.post(
        f"/v1/workspaces/{workspace_id}/uploads",
        json=upload_body(data, **overrides),
        headers=as_user(user),
    )


async def complete(
    client: httpx.AsyncClient, workspace_id: uuid.UUID, user: UserRef, upload_id: str
) -> httpx.Response:
    return await client.post(
        f"/v1/workspaces/{workspace_id}/uploads/{upload_id}/complete", headers=as_user(user)
    )


async def upload_document(
    client: httpx.AsyncClient,
    storage: FakeStorage,
    workspace_id: uuid.UUID,
    user: UserRef,
    data: bytes = PDF,
    **overrides: Any,
) -> dict[str, Any]:
    """Start, put the bytes (as the browser would), complete. Returns the document JSON."""
    ticket = (await start(client, workspace_id, user, data, **overrides)).json()
    assert ticket["kind"] == "upload", ticket
    storage.put(ticket["path"], data)
    response = await complete(client, workspace_id, user, ticket["upload_id"])
    assert response.status_code == 201, response.text
    document: dict[str, Any] = response.json()
    return document
