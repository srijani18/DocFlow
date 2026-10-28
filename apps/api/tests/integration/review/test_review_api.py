import copy
import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.models import Document
from app.extractions.models import Extraction
from app.review.models import Correction
from app.storage.fake import FakeStorage
from app.validation.gstin import with_valid_checksum
from tests.integration.validation.test_issues_api import validated
from tests.support.documents import PDF, as_user, upload_document
from tests.support.identity import TwoWorkspaces
from tests.support.samples import sample_truth

INVOICE = sample_truth("synthetic-invoice-001")["data"]


def corrected(**changes: Any) -> dict[str, Any]:
    """The stored invoice with some fields changed (dotted paths as `__`)."""
    data: dict[str, Any] = copy.deepcopy(INVOICE)
    for path, value in changes.items():
        *parents, last = path.split("__")
        node = data
        for part in parents:
            node = node[int(part)] if isinstance(node, list) else node[part]
        node[last] = value
    return data


def fixed_invoice() -> dict[str, Any]:
    """Every check passes: valid GSTINs."""
    return corrected(
        vendor__gstin=with_valid_checksum(INVOICE["vendor"]["gstin"][:14]),
        buyer__gstin=with_valid_checksum(INVOICE["buyer"]["gstin"][:14]),
    )


async def in_review(
    client: httpx.AsyncClient,
    storage: FakeStorage,
    session: AsyncSession,
    w: TwoWorkspaces,
    *,
    data: bytes = PDF,
) -> str:
    """A document waiting for review: model version 1, with an open `totals` error."""
    document = await upload_document(client, storage, w.a.id, w.a_admin, data)
    await validated(session, w, document["id"])
    return str(document["id"])


async def corrections_for(session: AsyncSession, document_id: str) -> list[Correction]:
    rows = await session.scalars(
        select(Correction).where(Correction.document_id == uuid.UUID(document_id))
    )
    return list(rows)


async def test_ac4_save_stores_a_human_version_with_corrections(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
) -> None:
    w = two_workspaces
    document_id = await in_review(db_client, fake_storage, db_session, w)
    base = f"/v1/workspaces/{w.a.id}/documents/{document_id}"

    response = await db_client.put(
        f"{base}/extraction",
        json={"base_version": 1, "data": corrected(vendor__name="Kaveri Fasteners Pvt Ltd")},
        headers=as_user(w.a_reviewer),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["version"], body["source"]) == (2, "human")
    assert body["data"]["vendor"]["name"] == "Kaveri Fasteners Pvt Ltd"
    assert body["confidence"]["vendor.name"] == 1.0
    [correction] = await corrections_for(db_session, document_id)
    assert (correction.path, correction.old_value, correction.new_value) == (
        "vendor.name",
        "Kaveri Fasteners Private Limited",
        "Kaveri Fasteners Pvt Ltd",
    )
    assert correction.user_id == w.a_reviewer.id
    detail = (await db_client.get(base, headers=as_user(w.a_admin))).json()
    assert detail["vendor_name"] == "Kaveri Fasteners Pvt Ltd"
    assert detail["status"] == "NEEDS_REVIEW"
    # The checks ran again on version 2 (the sample's GSTINs fail their checksum).
    issues = (await db_client.get(f"{base}/issues", headers=as_user(w.a_admin))).json()["items"]
    assert {i["check_name"] for i in issues} >= {"gstin"}


async def test_ac4_amounts_stay_exact(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
) -> None:
    w = two_workspaces
    document_id = await in_review(db_client, fake_storage, db_session, w)
    base = f"/v1/workspaces/{w.a.id}/documents/{document_id}"

    await db_client.put(
        f"{base}/extraction",
        json={"base_version": 1, "data": corrected(total__amount=16826.85)},
        headers=as_user(w.a_admin),
    )

    detail = (await db_client.get(base, headers=as_user(w.a_admin))).json()
    assert detail["total_amount"] == "16826.85"


async def test_unchanged_save_adds_no_version(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
) -> None:
    w = two_workspaces
    document_id = await in_review(db_client, fake_storage, db_session, w)

    response = await db_client.put(
        f"/v1/workspaces/{w.a.id}/documents/{document_id}/extraction",
        json={"base_version": 1, "data": INVOICE},
        headers=as_user(w.a_admin),
    )

    assert response.json()["version"] == 1
    assert await corrections_for(db_session, document_id) == []


async def test_ac6_save_on_an_outdated_version_is_rejected(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
) -> None:
    w = two_workspaces
    document_id = await in_review(db_client, fake_storage, db_session, w)
    url = f"/v1/workspaces/{w.a.id}/documents/{document_id}/extraction"
    first = await db_client.put(
        url,
        json={"base_version": 1, "data": corrected(invoice_number="A")},
        headers=as_user(w.a_admin),
    )

    second = await db_client.put(
        url,
        json={"base_version": 1, "data": corrected(invoice_number="B")},
        headers=as_user(w.a_reviewer),
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["title"] == "This document changed since you opened it"
    current = (await db_client.get(url, headers=as_user(w.a_admin))).json()
    assert (current["version"], current["data"]["invoice_number"]) == (2, "A")


async def test_ac3_invalid_data_is_rejected_with_the_field(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
) -> None:
    w = two_workspaces
    document_id = await in_review(db_client, fake_storage, db_session, w)

    response = await db_client.put(
        f"/v1/workspaces/{w.a.id}/documents/{document_id}/extraction",
        json={"base_version": 1, "data": corrected(invoice_date="14-08-2026")},
        headers=as_user(w.a_admin),
    )

    assert response.status_code == 422
    assert [e["field"] for e in response.json()["errors"]] == ["data.invoice_date"]
    assert await corrections_for(db_session, document_id) == []


async def test_ac5_approve_saves_changes_then_approves(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
) -> None:
    w = two_workspaces
    document_id = await in_review(db_client, fake_storage, db_session, w)

    response = await db_client.post(
        f"/v1/workspaces/{w.a.id}/documents/{document_id}/approve",
        json={"version": 1, "data": fixed_invoice()},
        headers=as_user(w.a_reviewer),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["approved_by_agent"]) == ("APPROVED", False)
    assert body["approved_at"] is not None
    row = (
        await db_session.scalars(select(Document).where(Document.id == uuid.UUID(document_id)))
    ).one()
    version = await db_session.scalar(
        select(Extraction.version).where(Extraction.id == row.approved_extraction_id)
    )
    assert (row.approved_by_user_id, version) == (w.a_reviewer.id, 2)
    assert {c.path for c in await corrections_for(db_session, document_id)} == {
        "vendor.gstin",
        "buyer.gstin",
    }


async def test_errors_need_approve_anyway(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
) -> None:
    w = two_workspaces
    document_id = await in_review(db_client, fake_storage, db_session, w)
    url = f"/v1/workspaces/{w.a.id}/documents/{document_id}/approve"

    refused = await db_client.post(url, json={"version": 1}, headers=as_user(w.a_admin))
    accepted = await db_client.post(
        url, json={"version": 1, "accept_errors": True}, headers=as_user(w.a_admin)
    )

    assert refused.status_code == 409
    assert refused.json()["title"] == "This document has unresolved errors"
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "APPROVED"


async def test_approved_documents_are_read_only(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
) -> None:
    w = two_workspaces
    document_id = await in_review(db_client, fake_storage, db_session, w)
    base = f"/v1/workspaces/{w.a.id}/documents/{document_id}"
    await db_client.post(
        f"{base}/approve", json={"version": 1, "accept_errors": True}, headers=as_user(w.a_admin)
    )

    save = await db_client.put(
        f"{base}/extraction",
        json={"base_version": 1, "data": corrected(invoice_number="X")},
        headers=as_user(w.a_admin),
    )
    again = await db_client.post(
        f"{base}/approve", json={"version": 1, "accept_errors": True}, headers=as_user(w.a_admin)
    )

    assert [save.status_code, again.status_code] == [409, 409]


@pytest.mark.parametrize("action", ["save", "approve"])
async def test_ac7_other_workspace_gets_not_found(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
    action: str,
) -> None:
    w = two_workspaces
    document_id = await in_review(db_client, fake_storage, db_session, w)
    responses = []
    for workspace in (w.a.id, w.b.id):
        base = f"/v1/workspaces/{workspace}/documents/{document_id}"
        if action == "save":
            request = db_client.put(
                f"{base}/extraction",
                json={"base_version": 1, "data": corrected(invoice_number="X")},
                headers=as_user(w.b_admin),
            )
        else:
            request = db_client.post(
                f"{base}/approve",
                json={"version": 1, "accept_errors": True},
                headers=as_user(w.b_admin),
            )
        responses.append(await request)

    assert [r.status_code for r in responses] == [404, 404]
    assert await corrections_for(db_session, document_id) == []


async def test_ac8_approved_without_edits_metric(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
) -> None:
    w = two_workspaces
    untouched = await in_review(db_client, fake_storage, db_session, w)
    edited = await in_review(db_client, fake_storage, db_session, w, data=PDF + b"%2\n")
    await in_review(db_client, fake_storage, db_session, w, data=PDF + b"%3\n")  # not approved
    base = f"/v1/workspaces/{w.a.id}"
    await db_client.post(
        f"{base}/documents/{untouched}/approve",
        json={"version": 1, "accept_errors": True},
        headers=as_user(w.a_admin),
    )
    await db_client.post(
        f"{base}/documents/{edited}/approve",
        json={"version": 1, "data": fixed_invoice()},
        headers=as_user(w.a_admin),
    )

    metrics = await db_client.get(f"{base}/metrics/review", headers=as_user(w.a_reviewer))
    other = await db_client.get(
        f"/v1/workspaces/{w.b.id}/metrics/review", headers=as_user(w.b_admin)
    )

    assert metrics.json() == {
        "approved": 2,
        "approved_without_edits": 1,
        "approved_by_agent": 0,
        "approved_without_edits_rate": 0.5,
    }
    assert other.json()["approved"] == 0


async def test_schema_endpoint_serves_bundled_schemas(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces
) -> None:
    w = two_workspaces

    found = await db_client.get("/v1/schemas/docflow/invoice/v1", headers=as_user(w.a_admin))
    missing = await db_client.get("/v1/schemas/docflow/nothing/v1", headers=as_user(w.a_admin))
    anonymous = await db_client.get("/v1/schemas/docflow/invoice/v1")

    assert found.status_code == 200
    assert "$ref" not in found.text  # bundled: common definitions inlined
    assert found.json()["properties"]["invoice_number"]
    assert [missing.status_code, anonymous.status_code] == [404, 401]
