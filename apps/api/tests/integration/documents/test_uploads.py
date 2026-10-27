import asyncio
import hashlib
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core import rls
from app.core.tenancy import WorkspaceScope
from app.documents import service
from app.documents.models import Document
from app.storage.fake import FakeStorage
from tests.support.clock import FrozenClock
from tests.support.documents import PDF, complete, start, upload_document
from tests.support.identity import TwoWorkspaces, make_two_workspaces


async def test_ac1_complete_creates_uploaded_document(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces, fake_storage: FakeStorage
) -> None:
    w = two_workspaces
    response = await start(db_client, w.a.id, w.a_admin)
    assert response.status_code == 201
    ticket = response.json()
    assert ticket["kind"] == "upload"
    assert ticket["path"] == f"{w.a.id}/{ticket['upload_id']}"
    assert ticket["bucket"] == fake_storage.bucket
    assert ticket["token"]

    fake_storage.put(ticket["path"], PDF)
    done = await complete(db_client, w.a.id, w.a_admin, ticket["upload_id"])

    assert done.status_code == 201
    document = done.json()
    assert document["status"] == "UPLOADED"
    assert (document["filename"], document["size_bytes"]) == ("invoice.pdf", len(PDF))
    assert document["sha256"] == hashlib.sha256(PDF).hexdigest()


@pytest.mark.parametrize(
    ("override", "field"),
    [
        ({"content_type": "application/zip"}, "content_type"),
        ({"size_bytes": 10 * 1024 * 1024 + 1}, "size_bytes"),
        ({"size_bytes": 0}, "size_bytes"),
        ({"sha256": "not-a-hash"}, "sha256"),
        ({"sha256": "A" * 64}, "sha256"),
        ({"filename": "   "}, "filename"),
    ],
)
async def test_ac2_rejects_type_size_and_bad_hash_with_field_errors(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    override: dict[str, Any],
    field: str,
) -> None:
    response = await start(db_client, two_workspaces.a.id, two_workspaces.a_admin, **override)

    assert response.status_code == 422
    assert response.json()["type"].endswith("/validation")
    assert [error["field"] for error in response.json()["errors"]] == [field]
    assert fake_storage.signed_uploads == []


async def test_ac3_duplicate_returns_existing_without_ticket(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces, fake_storage: FakeStorage
) -> None:
    w = two_workspaces
    original = await upload_document(db_client, fake_storage, w.a.id, w.a_admin)

    response = await start(db_client, w.a.id, w.a_reviewer, filename="renamed.pdf")

    assert response.status_code == 200
    assert response.json()["kind"] == "duplicate"
    assert response.json()["document"]["id"] == original["id"]
    assert response.json()["document"]["filename"] == "invoice.pdf"
    assert len(fake_storage.signed_uploads) == 1


async def test_ac3_same_file_other_workspace_is_new(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces, fake_storage: FakeStorage
) -> None:
    w = two_workspaces
    await upload_document(db_client, fake_storage, w.a.id, w.a_admin)

    response = await start(db_client, w.b.id, w.b_admin)

    assert response.status_code == 201
    assert response.json()["kind"] == "upload"


async def test_ac3_identical_uploads_started_together_settle_on_one_document(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces, fake_storage: FakeStorage
) -> None:
    w = two_workspaces
    first = (await start(db_client, w.a.id, w.a_admin)).json()
    second = (await start(db_client, w.a.id, w.a_reviewer)).json()  # no document yet: a ticket
    fake_storage.put(first["path"], PDF)
    fake_storage.put(second["path"], PDF)

    created = await complete(db_client, w.a.id, w.a_admin, first["upload_id"])
    resolved = await complete(db_client, w.a.id, w.a_reviewer, second["upload_id"])

    assert (created.status_code, resolved.status_code) == (201, 200)
    assert resolved.json()["id"] == created.json()["id"]


@pytest.mark.parametrize("stored", [None, PDF + b"extra"])
async def test_ac4_missing_or_wrong_size_object_rejected(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
    stored: bytes | None,
) -> None:
    w = two_workspaces
    ticket = (await start(db_client, w.a.id, w.a_admin)).json()
    if stored is not None:
        fake_storage.put(ticket["path"], stored)

    response = await complete(db_client, w.a.id, w.a_admin, ticket["upload_id"])

    assert response.status_code == 409
    assert response.json()["type"].endswith("/upload-incomplete")
    assert await db_session.scalar(select(func.count()).select_from(Document)) == 0


async def test_ac5_double_complete_returns_one_document(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces, fake_storage: FakeStorage
) -> None:
    w = two_workspaces
    ticket = (await start(db_client, w.a.id, w.a_admin)).json()
    fake_storage.put(ticket["path"], PDF)

    first = await complete(db_client, w.a.id, w.a_admin, ticket["upload_id"])
    second = await complete(db_client, w.a.id, w.a_admin, ticket["upload_id"])

    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json()["id"] == second.json()["id"]


async def test_ac5_concurrent_identical_uploads_one_document(
    committing_engine: AsyncEngine,
) -> None:
    """Two completions racing on separate connections, as two browser tabs would."""
    system = {rls.DEFAULT: rls.SYSTEM}
    async with AsyncSession(committing_engine, expire_on_commit=False, info=system) as setup:
        w = await make_two_workspaces(setup)
        await setup.commit()
    scope_a = WorkspaceScope(workspace_id=w.a.id, user_id=w.a_admin.id, role="admin")
    storage, clock = FakeStorage(), FrozenClock()
    # As in the app, under row-level security for workspace A (F14).
    with rls.acting_for(w.a.id):
        async with AsyncSession(committing_engine, expire_on_commit=False) as session:
            tickets = [
                await service.start_upload(
                    session,
                    storage,
                    clock,
                    scope_a,
                    filename="x.pdf",
                    content_type="application/pdf",
                    size_bytes=len(PDF),
                    sha256=hashlib.sha256(PDF).hexdigest(),
                )
                for _ in range(2)
            ]
            await session.commit()
        upload_ids = []
        for ticket in tickets:
            assert isinstance(ticket, service.NewUpload)
            storage.put(ticket.signed.path, PDF)
            upload_ids.append(str(ticket.upload.id))

        async def complete_in_own_transaction(upload_id: str) -> tuple[str, bool]:
            async with AsyncSession(committing_engine) as session, session.begin():
                document, created = await service.complete_upload(
                    session, storage, clock, scope_a, upload_id
                )
                return str(document.id), created

        results = await asyncio.gather(*(complete_in_own_transaction(u) for u in upload_ids * 2))

    assert len({document_id for document_id, _ in results}) == 1
    assert sum(created for _, created in results) == 1


async def test_ac10_reviewer_can_upload(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces, fake_storage: FakeStorage
) -> None:
    w = two_workspaces
    document = await upload_document(db_client, fake_storage, w.a.id, w.a_reviewer)

    assert document["status"] == "UPLOADED"


async def test_ac11_non_member_gets_404(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces, fake_storage: FakeStorage
) -> None:
    w = two_workspaces
    response = await start(db_client, w.b.id, w.a_admin)

    assert response.status_code == 404
    assert fake_storage.signed_uploads == []


async def test_ac11_other_workspace_upload_404(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces, fake_storage: FakeStorage
) -> None:
    w = two_workspaces
    ticket = (await start(db_client, w.a.id, w.a_admin)).json()
    fake_storage.put(ticket["path"], PDF)

    via_b = await complete(db_client, w.b.id, w.b_admin, ticket["upload_id"])
    malformed = await complete(db_client, w.a.id, w.a_admin, "not-a-uuid")

    assert (via_b.status_code, malformed.status_code) == (404, 404)


async def test_expired_upload_cannot_be_completed(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    clock: FrozenClock,
) -> None:
    w = two_workspaces
    ticket = (await start(db_client, w.a.id, w.a_admin)).json()
    fake_storage.put(ticket["path"], PDF)
    clock.advance(hours=2, seconds=1)

    response = await complete(db_client, w.a.id, w.a_admin, ticket["upload_id"])

    assert response.status_code == 404
