import uuid

import httpx
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import WorkspaceScope
from app.documents.models import Document
from app.extractions import service as extractions
from app.storage.fake import FakeStorage
from app.validation import service
from app.validation.checks import Issue
from tests.integration.extractions.test_extraction_api import store_extraction
from tests.support.documents import as_user, upload_document
from tests.support.identity import TwoWorkspaces

TOTALS = Issue("totals", "error", ("total.amount",), "Subtotal plus taxes isn't the total.")
GSTIN = Issue("gstin", "error", ("vendor.gstin",), "The GSTIN checksum is wrong.")
VENDOR = Issue("known_vendor", "info", ("vendor",), "First document from this vendor.")


async def validated(
    session: AsyncSession, w: TwoWorkspaces, document_id: str, *, workspace: str = "a"
) -> None:
    """An extraction with issues, and the document waiting for review."""
    await store_extraction(session, w, document_id, workspace=workspace)
    ws, user = (w.a, w.a_admin) if workspace == "a" else (w.b, w.b_admin)
    scope = WorkspaceScope(workspace_id=ws.id, user_id=user.id, role="admin")
    extraction = await extractions.get_current(session, scope, document_id)
    await service.record_issues(
        session,
        scope,
        document_id=uuid.UUID(document_id),
        extraction_id=extraction.id,
        remaining=[TOTALS, VENDOR],
        fixed=[GSTIN],
    )
    await session.execute(
        update(Document).where(Document.id == uuid.UUID(document_id)).values(status="NEEDS_REVIEW")
    )
    await session.commit()


async def test_ac2_issues_listed_with_paths_severity_and_fixed_flag(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
) -> None:
    w = two_workspaces
    document = await upload_document(db_client, fake_storage, w.a.id, w.a_admin)
    await validated(db_session, w, document["id"])
    base = f"/v1/workspaces/{w.a.id}/documents/{document['id']}"

    response = await db_client.get(f"{base}/issues", headers=as_user(w.a_reviewer))

    assert response.status_code == 200
    got = {
        (i["check_name"], i["severity"], tuple(i["paths"]), i["fixed_by_agent"])
        for i in response.json()["items"]
    }
    assert got == {
        ("totals", "error", ("total.amount",), False),
        ("known_vendor", "info", ("vendor",), False),
        ("gstin", "error", ("vendor.gstin",), True),
    }


async def test_document_shows_open_issue_counts_and_approval(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
) -> None:
    w = two_workspaces
    document = await upload_document(db_client, fake_storage, w.a.id, w.a_admin)
    await validated(db_session, w, document["id"])
    base = f"/v1/workspaces/{w.a.id}"

    detail = await db_client.get(f"{base}/documents/{document['id']}", headers=as_user(w.a_admin))
    listed = await db_client.get(f"{base}/documents", headers=as_user(w.a_admin))

    expected = {"error": 1, "warning": 0, "info": 1}  # the fixed GSTIN issue isn't counted
    assert detail.status_code == 200, detail.text
    assert detail.json()["issue_counts"] == expected
    assert listed.json()["items"][0]["issue_counts"] == expected
    assert (detail.json()["approved_at"], detail.json()["approved_by_agent"]) == (None, False)


async def test_no_counts_while_processing(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces, fake_storage: FakeStorage
) -> None:
    w = two_workspaces
    document = await upload_document(db_client, fake_storage, w.a.id, w.a_admin)

    assert document["issue_counts"] is None
    response = await db_client.get(
        f"/v1/workspaces/{w.a.id}/documents/{document['id']}/issues", headers=as_user(w.a_admin)
    )
    assert response.status_code == 404


async def test_other_workspace_issues_404(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
) -> None:
    w = two_workspaces
    document = await upload_document(db_client, fake_storage, w.b.id, w.b_admin)
    await validated(db_session, w, document["id"], workspace="b")

    responses = [
        await db_client.get(
            f"/v1/workspaces/{ws}/documents/{document['id']}/issues", headers=as_user(w.a_admin)
        )
        for ws in (w.b.id, w.a.id)
    ]

    assert [response.status_code for response in responses] == [404, 404]
    assert all("checksum" not in response.text for response in responses)
