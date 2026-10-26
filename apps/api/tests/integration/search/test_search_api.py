import copy
import uuid
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import WorkspaceScope
from app.documents.models import Document
from app.extractions import service as extractions
from app.extractions.envelope import SCHEMA_BY_DOC_TYPE
from app.llm.providers.fake import fake_embedding
from app.search import service
from app.search.embed_text import embedding_text
from app.search.models import EMBEDDING_DIMENSIONS, DocumentEmbedding
from app.storage.fake import FakeStorage
from tests.integration.conftest import FakeQueryEmbedder
from tests.support.documents import PDF, as_user, upload_document
from tests.support.identity import TwoWorkspaces
from tests.support.samples import sample_truth

INVOICE = sample_truth("synthetic-invoice-001")["data"]  # Kaveri Fasteners, steel brackets
RECEIPT = sample_truth("synthetic-receipt-001")["data"]


@pytest.fixture(autouse=True)
def lenient_meaning(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fake embeddings are a bag of words: a short query is far from a long document
    even when it shares words, so these tests accept any shared word as "meaning"."""
    monkeypatch.setattr(service, "MAX_DISTANCE", 0.97)
    monkeypatch.setattr(service, "MARGIN", 1.0)


async def indexed(  # a searchable document needs all of these
    client: httpx.AsyncClient,
    storage: FakeStorage,
    session: AsyncSession,
    w: TwoWorkspaces,
    *,
    doc_type: str,
    data: dict[str, Any],
    workspace: str = "a",
    status: str = "NEEDS_REVIEW",
    filename: str = "scan.pdf",
) -> str:
    """Uploaded, extracted and embedded, as the pipeline and embed job would leave it."""
    ws, user = (w.a, w.a_admin) if workspace == "a" else (w.b, w.b_admin)
    document = await upload_document(
        client, storage, ws.id, user, PDF + uuid.uuid4().bytes, filename=filename
    )
    scope = WorkspaceScope(workspace_id=ws.id, user_id=user.id, role="admin")
    document_id = uuid.UUID(document["id"])
    extraction = await extractions.record_model_extraction(
        session,
        scope,
        document_id=document_id,
        doc_type=doc_type,
        schema_id=SCHEMA_BY_DOC_TYPE[doc_type],
        data=data,
        confidence={},
        prompt_version="extract/v1",
        llm_call_id=None,  # type: ignore[arg-type]
        generation=1,
    )
    await session.execute(
        update(Document).where(Document.id == document_id).values(doc_type=doc_type, status=status)
    )
    session.add(
        DocumentEmbedding(
            document_id=document_id,
            workspace_id=ws.id,
            extraction_id=extraction.id,
            model="fake-embedding",
            embedding=fake_embedding(embedding_text(doc_type, data), EMBEDDING_DIMENSIONS),
        )
    )
    await session.commit()
    return str(document_id)


async def search(
    client: httpx.AsyncClient, w: TwoWorkspaces, workspace: str = "a", **params: Any
) -> dict[str, Any]:
    ws, user = (w.a, w.a_admin) if workspace == "a" else (w.b, w.b_admin)
    response = await client.get(
        f"/v1/workspaces/{ws.id}/search", params=params, headers=as_user(user)
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def ids(body: dict[str, Any]) -> list[str]:
    return [item["document"]["id"] for item in body["items"]]


async def test_ac1_ac2_keyword_matches_numbers_prefixes_and_gstins(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
) -> None:
    w = two_workspaces
    invoice = await indexed(
        db_client, fake_storage, db_session, w, doc_type="invoice", data=INVOICE
    )
    await indexed(db_client, fake_storage, db_session, w, doc_type="receipt", data=RECEIPT)
    gstin = INVOICE["vendor"]["gstin"]

    for query in (
        INVOICE["invoice_number"],  # SYN/2026-27/0142
        "SYN2026270142",
        "kaver",
        f"{gstin[:7]} {gstin[7:]}".lower(),
    ):
        body = await search(db_client, w, q=query)
        assert ids(body)[:1] == [invoice], query
        assert body["items"][0]["matched"] in {"keyword", "both"}

    snippet = (await search(db_client, w, q="kaveri"))["items"][0]["snippet"]
    assert "[[Kaveri]]" in snippet


async def test_ac3_meaning_finds_what_keywords_miss(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
) -> None:
    w = two_workspaces
    invoice = await indexed(
        db_client, fake_storage, db_session, w, doc_type="invoice", data=INVOICE
    )

    # "supplier" is on no document, so the keyword query (all words) finds nothing.
    body = await search(db_client, w, q="fasteners supplier")

    assert [(item["document"]["id"], item["matched"]) for item in body["items"]] == [
        (invoice, "meaning")
    ]
    assert body["semantic"] is True


async def test_ac5_without_embeddings_keyword_only_with_notice(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
    query_embedder: FakeQueryEmbedder,
) -> None:
    w = two_workspaces
    invoice = await indexed(
        db_client, fake_storage, db_session, w, doc_type="invoice", data=INVOICE
    )
    query_embedder.available = False

    meaning_only = await search(db_client, w, q="fasteners supplier")
    keyword = await search(db_client, w, q="kaveri")

    assert (ids(meaning_only), meaning_only["semantic"]) == ([], False)
    assert (ids(keyword), keyword["items"][0]["matched"]) == ([invoice], "keyword")


async def test_short_queries_skip_meaning(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
    query_embedder: FakeQueryEmbedder,
) -> None:
    w = two_workspaces
    await indexed(db_client, fake_storage, db_session, w, doc_type="invoice", data=INVOICE)

    body = await search(db_client, w, q="ka")

    assert query_embedder.queries == []
    assert body["semantic"] is True  # nothing was unavailable


async def test_ac4_filters_with_and_without_text(
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
        db_client, fake_storage, db_session, w, doc_type="receipt", data=RECEIPT, status="APPROVED"
    )
    total = Decimal(str(INVOICE["total"]["amount"]))

    # Newest first; both were created in one transaction, so their times tie here.
    assert set(ids(await search(db_client, w))) == {receipt, invoice}
    assert ids(await search(db_client, w, doc_type="invoice")) == [invoice]
    assert ids(await search(db_client, w, status="APPROVED")) == [receipt]
    assert ids(await search(db_client, w, vendor="kaveri")) == [invoice]
    assert ids(await search(db_client, w, date_from="2026-08-14", date_to="2026-08-14")) == [
        invoice
    ]
    assert ids(await search(db_client, w, amount_min=str(total), amount_max=str(total))) == [
        invoice
    ]
    assert ids(await search(db_client, w, q="kaveri", doc_type="receipt")) == []


async def test_documents_without_extraction_are_found_by_file_name(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces, fake_storage: FakeStorage
) -> None:
    w = two_workspaces
    document = await upload_document(
        db_client, fake_storage, w.a.id, w.a_admin, filename="march-electricity_bill.pdf"
    )

    assert ids(await search(db_client, w, q="electricity")) == [document["id"]]


async def test_ac9_other_workspaces_never_appear(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
) -> None:
    w = two_workspaces
    theirs = await indexed(
        db_client, fake_storage, db_session, w, doc_type="invoice", data=INVOICE, workspace="b"
    )

    for query in ("kaveri", "fasteners supplier", ""):
        assert ids(await search(db_client, w, q=query)) == [], query
    assert ids(await search(db_client, w, workspace="b", q="kaveri")) == [theirs]
    outsider = await db_client.get(
        f"/v1/workspaces/{w.b.id}/search", params={"q": "kaveri"}, headers=as_user(w.a_admin)
    )
    assert outsider.status_code == 404


async def test_ac6_a_reviewers_save_updates_the_keyword_index(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
) -> None:
    w = two_workspaces
    document_id = await indexed(
        db_client, fake_storage, db_session, w, doc_type="invoice", data=INVOICE
    )
    renamed = copy.deepcopy(INVOICE)
    renamed["vendor"]["name"] = "Godavari Traders"

    saved = await db_client.put(
        f"/v1/workspaces/{w.a.id}/documents/{document_id}/extraction",
        json={"base_version": 1, "data": renamed},
        headers=as_user(w.a_admin),
    )

    assert saved.status_code == 200, saved.text
    assert ids(await search(db_client, w, q="godavari")) == [document_id]
    # The old embedding was of version 1: it no longer counts until re-embedded.
    assert ids(await search(db_client, w, q="fasteners supplier")) == []


async def test_paging_and_bad_cursor(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
) -> None:
    w = two_workspaces
    for _ in range(3):
        await indexed(db_client, fake_storage, db_session, w, doc_type="invoice", data=INVOICE)

    first = await search(db_client, w, q="kaveri", limit=2)
    second = await search(db_client, w, q="kaveri", limit=2, cursor=first["next_cursor"])
    bad = await db_client.get(
        f"/v1/workspaces/{w.a.id}/search",
        params={"q": "x", "cursor": "nope"},
        headers=as_user(w.a_admin),
    )

    assert len(ids(first)) == 2
    assert len(ids(second)) == 1
    assert second["next_cursor"] is None
    assert set(ids(first)).isdisjoint(ids(second))
    assert bad.status_code == 422
