import json
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.fake import FakeStorage
from evals.import_reviews import export
from evals.runner import load_manifest
from tests.integration.review.test_review_api import fixed_invoice, in_review
from tests.support.documents import PDF, as_user
from tests.support.identity import TwoWorkspaces


async def test_ac9_exports_human_approved_documents_of_one_workspace(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    w = two_workspaces
    approved = await in_review(db_client, fake_storage, db_session, w)
    await in_review(db_client, fake_storage, db_session, w, data=PDF + b"%2\n")  # not approved
    await db_client.post(
        f"/v1/workspaces/{w.a.id}/documents/{approved}/approve",
        json={"version": 1, "data": fixed_invoice()},
        headers=as_user(w.a_reviewer),
    )

    entries = await export(db_session, fake_storage, w.a.id, tmp_path)
    nothing = await export(db_session, fake_storage, w.b.id, tmp_path / "b")

    [entry] = entries
    assert entry["id"] == f"review-{approved}"
    assert (entry["source"], entry["corrections"]) == ("review", 2)
    assert entry["truth"]["vendor"]["gstin"] == fixed_invoice()["vendor"]["gstin"]
    assert (tmp_path / entry["file"]).read_bytes() == PDF
    version, documents = load_manifest(tmp_path / "manifest.v2.json")
    assert (version, [d.id for d in documents]) == (2, [entry["id"]])
    assert nothing == []
    assert json.loads((tmp_path / "b" / "manifest.v2.json").read_text())["documents"] == []
