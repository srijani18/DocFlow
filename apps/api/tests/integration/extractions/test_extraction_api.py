import uuid
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import WorkspaceScope
from app.extractions import service
from app.llm.models import LlmCall
from app.storage.fake import FakeStorage
from tests.support.documents import as_user, upload_document
from tests.support.identity import TwoWorkspaces
from tests.support.samples import sample_truth

INVOICE = sample_truth("synthetic-invoice-001")["data"]


async def store_extraction(
    session: AsyncSession, w: TwoWorkspaces, document_id: str, workspace: str = "a"
) -> None:
    ws = getattr(w, workspace)
    user = w.a_admin if workspace == "a" else w.b_admin
    scope = WorkspaceScope(workspace_id=ws.id, user_id=user.id, role="admin")
    call = LlmCall(
        workspace_id=ws.id,
        task="extract",
        provider="fake",
        model="fake-model",
        prompt_version="extract/v1",
        attempt=1,
        outcome="ok",
        latency_ms=1,
    )
    session.add(call)
    await session.flush()
    await service.record_model_extraction(
        session,
        scope,
        document_id=uuid.UUID(document_id),
        doc_type="invoice",
        schema_id="docflow/invoice/v1",
        data=INVOICE,
        confidence={"vendor.gstin": Decimal("0.6"), "total.amount": Decimal("0.99")},
        prompt_version="extract/v1",
        llm_call_id=call.id,
        generation=1,
    )
    await session.commit()


async def test_ac6_returns_current_extraction(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
) -> None:
    w = two_workspaces
    document = await upload_document(db_client, fake_storage, w.a.id, w.a_admin)
    await store_extraction(db_session, w, document["id"])
    base = f"/v1/workspaces/{w.a.id}/documents/{document['id']}"

    extraction = await db_client.get(f"{base}/extraction", headers=as_user(w.a_reviewer))
    detail = await db_client.get(base, headers=as_user(w.a_reviewer))

    assert extraction.status_code == 200
    body = extraction.json()
    assert (body["version"], body["source"], body["schema_id"]) == (
        1,
        "model",
        "docflow/invoice/v1",
    )
    assert body["data"]["invoice_number"] == "SYN/2026-27/0142"
    assert body["confidence"] == {"vendor.gstin": 0.6, "total.amount": 0.99}
    assert body["prompt_version"] == "extract/v1"
    summary = detail.json()
    assert (summary["vendor_name"], summary["document_date"], summary["currency"]) == (
        "Kaveri Fasteners Private Limited",
        "2026-08-14",
        "INR",
    )
    assert summary["total_amount"] == "16826.80"


async def test_no_extraction_yet_is_404(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces, fake_storage: FakeStorage
) -> None:
    w = two_workspaces
    document = await upload_document(db_client, fake_storage, w.a.id, w.a_admin)

    response = await db_client.get(
        f"/v1/workspaces/{w.a.id}/documents/{document['id']}/extraction",
        headers=as_user(w.a_admin),
    )

    assert response.status_code == 404


async def test_other_workspace_extraction_404(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
) -> None:
    w = two_workspaces
    document = await upload_document(db_client, fake_storage, w.b.id, w.b_admin)
    await store_extraction(db_session, w, document["id"], workspace="b")

    responses = [
        await db_client.get(
            f"/v1/workspaces/{ws}/documents/{document['id']}/extraction", headers=as_user(w.a_admin)
        )
        for ws in (w.b.id, w.a.id)
    ]

    assert [response.status_code for response in responses] == [404, 404]
    assert all("Kaveri" not in response.text for response in responses)


async def test_ac6_fields_come_back_in_schema_order(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
) -> None:
    w = two_workspaces
    document = await upload_document(db_client, fake_storage, w.a.id, w.a_admin)
    await store_extraction(db_session, w, document["id"])

    response = await db_client.get(
        f"/v1/workspaces/{w.a.id}/documents/{document['id']}/extraction",
        headers=as_user(w.a_admin),
    )

    data = response.json()["data"]
    assert list(data) == list(INVOICE)  # invoice_number first, total last
    assert list(data["vendor"]) == ["name", "gstin", "address"]
    assert list(data["line_items"][0]) == [
        "description",
        "hsn_sac",
        "quantity",
        "unit_price",
        "amount",
    ]
