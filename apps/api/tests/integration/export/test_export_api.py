import copy
import csv
import io
import json
import uuid
import zipfile
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.models import Document
from app.export import service
from app.export.csv_writer import BOM
from app.storage.fake import FakeStorage
from tests.integration.search.test_search_api import indexed
from tests.support.documents import as_user
from tests.support.identity import TwoWorkspaces
from tests.support.samples import sample_truth

INVOICE = sample_truth("synthetic-invoice-001")["data"]
RECEIPT = sample_truth("synthetic-receipt-001")["data"]


async def approve(session: AsyncSession, document_id: str, *, by_agent: bool = True) -> None:
    """Approved by the agent, with the current version as the approved one."""
    document = uuid.UUID(document_id)
    await session.execute(
        update(Document)
        .where(Document.id == document)
        .values(
            status="APPROVED",
            approved_by_agent=by_agent,
            approved_at=Document.created_at,
            approved_extraction_id=Document.current_extraction_id,
        )
    )
    await session.commit()


async def export(
    client: httpx.AsyncClient, w: TwoWorkspaces, workspace: str = "a", **params: Any
) -> httpx.Response:
    ws, user = (w.a, w.a_admin) if workspace == "a" else (w.b, w.b_admin)
    return await client.get(f"/v1/workspaces/{ws.id}/export", params=params, headers=as_user(user))


def unzip(response: httpx.Response) -> dict[str, list[dict[str, str]]]:
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    files = {}
    for name in archive.namelist():
        text = archive.read(name).decode()
        assert text.startswith(BOM)
        files[name] = list(csv.DictReader(io.StringIO(text.removeprefix(BOM))))
    return files


async def test_ac1_ac2_csv_zip_of_approved_documents(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
) -> None:
    w = two_workspaces
    approved = await indexed(
        db_client, fake_storage, db_session, w, doc_type="invoice", data=INVOICE
    )
    await approve(db_session, approved)
    await indexed(db_client, fake_storage, db_session, w, doc_type="receipt", data=RECEIPT)

    response = await export(db_client, w)

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"].startswith(
        'attachment; filename="docflow-export-'
    )
    files = unzip(response)
    [document] = files["documents.csv"]
    assert (document["document_id"], document["number"], document["total"]) == (
        approved,
        "SYN/2026-27/0142",
        "16826.80",
    )
    assert (document["status"], document["approved_by"], document["corrections"]) == (
        "APPROVED",
        "agent",
        "0",
    )
    assert len(files["line_items.csv"]) == len(INVOICE["line_items"])
    assert {row["document_id"] for row in files["line_items.csv"]} == {approved}


async def test_ac1_ac8_include_unapproved_says_so_and_uses_the_current_version(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
) -> None:
    w = two_workspaces
    pending = await indexed(
        db_client, fake_storage, db_session, w, doc_type="receipt", data=RECEIPT
    )

    [row] = unzip(await export(db_client, w, include_unapproved="true"))["documents.csv"]

    assert (row["document_id"], row["status"], row["approved_by"]) == (
        pending,
        "NEEDS_REVIEW",
        "",
    )


async def test_ac8_the_approved_version_is_exported_not_a_newer_one(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
) -> None:
    w = two_workspaces
    document_id = await indexed(
        db_client, fake_storage, db_session, w, doc_type="invoice", data=INVOICE
    )
    await approve(db_session, document_id)
    # A later version (not possible through the API today, but the rule must hold).
    newer = copy.deepcopy(INVOICE)
    newer["invoice_number"] = "LATER"
    other = await indexed(db_client, fake_storage, db_session, w, doc_type="invoice", data=newer)
    async with db_session.begin_nested():
        current = (await db_session.get(Document, uuid.UUID(other))).current_extraction_id  # type: ignore[union-attr]
        await db_session.execute(
            update(Document)
            .where(Document.id == uuid.UUID(document_id))
            .values(current_extraction_id=current)
        )
    await db_session.commit()

    [row] = unzip(await export(db_client, w))["documents.csv"]

    assert row["number"] == "SYN/2026-27/0142"


async def test_ac3_json_keeps_exact_amounts(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
) -> None:
    w = two_workspaces
    document_id = await indexed(
        db_client, fake_storage, db_session, w, doc_type="invoice", data=INVOICE
    )
    await approve(db_session, document_id, by_agent=False)

    response = await export(db_client, w, format="json")

    assert response.headers["content-type"] == "application/json"
    [item] = json.loads(response.text, parse_float=Decimal)
    assert item["document"]["id"] == document_id
    assert item["data"]["total"]["amount"] == Decimal("16826.80")
    assert item["data"]["line_items"] == json.loads(
        json.dumps(INVOICE["line_items"]), parse_float=Decimal
    )


async def test_filters_and_text_select_what_search_shows(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
) -> None:
    w = two_workspaces
    invoice = await indexed(
        db_client, fake_storage, db_session, w, doc_type="invoice", data=INVOICE
    )
    receipt = await indexed(
        db_client, fake_storage, db_session, w, doc_type="receipt", data=RECEIPT
    )
    for document_id in (invoice, receipt):
        await approve(db_session, document_id)

    by_type = unzip(await export(db_client, w, doc_type="receipt"))["documents.csv"]
    by_text = unzip(await export(db_client, w, q="kaveri"))["documents.csv"]

    assert [row["document_id"] for row in by_type] == [receipt]
    assert [row["document_id"] for row in by_text] == [invoice]


async def test_empty_export_has_headers_only(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces
) -> None:
    files = unzip(await export(db_client, two_workspaces))

    assert files == {"documents.csv": [], "line_items.csv": []}


async def test_ac6_too_many_documents_asks_to_narrow(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    w = two_workspaces
    for _ in range(2):
        await approve(
            db_session,
            await indexed(db_client, fake_storage, db_session, w, doc_type="invoice", data=INVOICE),
        )
    monkeypatch.setattr(service, "MAX_DOCUMENTS", 1)

    response = await export(db_client, w)

    assert response.status_code == 422
    assert response.json()["title"] == "Too many documents to export"
    assert "Narrow the filters" in response.json()["detail"]


async def test_ac7_other_workspaces_never_export(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
) -> None:
    w = two_workspaces
    theirs = await indexed(
        db_client, fake_storage, db_session, w, doc_type="invoice", data=INVOICE, workspace="b"
    )
    await approve(db_session, theirs)

    mine = unzip(await export(db_client, w))["documents.csv"]
    outsider = await db_client.get(f"/v1/workspaces/{w.b.id}/export", headers=as_user(w.a_admin))

    assert mine == []
    assert outsider.status_code == 404
