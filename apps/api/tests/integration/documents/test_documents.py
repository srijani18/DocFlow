from datetime import timedelta

import httpx
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.models import Document
from app.storage.fake import FakeStorage
from tests.support.clock import FrozenClock
from tests.support.documents import as_user, upload_document
from tests.support.identity import TwoWorkspaces


async def test_ac8_list_newest_first_paginates_with_cursor(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
) -> None:
    w = two_workspaces
    ids = []
    for index in range(3):
        document = await upload_document(
            db_client, fake_storage, w.a.id, w.a_admin, data=b"%PDF" + bytes([index])
        )
        ids.append(document["id"])
    # One test transaction gives every row the same now(); spread them out in time.
    for age, document_id in enumerate(reversed(ids)):
        await db_session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(created_at=Document.created_at - timedelta(minutes=age))
        )
    await db_session.commit()
    url = f"/v1/workspaces/{w.a.id}/documents"

    first = (await db_client.get(url, params={"limit": 2}, headers=as_user(w.a_admin))).json()
    second = (
        await db_client.get(
            url, params={"limit": 2, "cursor": first["next_cursor"]}, headers=as_user(w.a_admin)
        )
    ).json()

    assert [item["id"] for item in first["items"]] == [ids[2], ids[1]]
    assert [item["id"] for item in second["items"]] == [ids[0]]
    assert second["next_cursor"] is None


async def test_ac8_invalid_cursor_is_a_field_error(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces
) -> None:
    w = two_workspaces
    response = await db_client.get(
        f"/v1/workspaces/{w.a.id}/documents",
        params={"cursor": "garbage"},
        headers=as_user(w.a_admin),
    )

    assert response.status_code == 422
    assert [error["field"] for error in response.json()["errors"]] == ["cursor"]


async def test_ac9_detail_and_file_url_signed_for_5_minutes(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    clock: FrozenClock,
) -> None:
    w = two_workspaces
    document = await upload_document(db_client, fake_storage, w.a.id, w.a_admin)
    base = f"/v1/workspaces/{w.a.id}/documents/{document['id']}"

    detail = await db_client.get(base, headers=as_user(w.a_reviewer))
    signed = await db_client.post(f"{base}/file-url", headers=as_user(w.a_reviewer))

    assert detail.json() == document
    assert signed.status_code == 200
    assert f"{w.a.id}/" in signed.json()["url"]
    expected = (clock.now() + timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    assert signed.json()["expires_at"] == expected


async def test_ac11_member_of_a_cannot_list_or_view_b(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces, fake_storage: FakeStorage
) -> None:
    w = two_workspaces
    b_document = await upload_document(db_client, fake_storage, w.b.id, w.b_admin)
    b_url = f"/v1/workspaces/{w.b.id}/documents"

    listing = await db_client.get(f"/v1/workspaces/{w.a.id}/documents", headers=as_user(w.a_admin))
    responses = [
        await db_client.get(b_url, headers=as_user(w.a_admin)),
        await db_client.get(f"{b_url}/{b_document['id']}", headers=as_user(w.a_admin)),
        await db_client.post(f"{b_url}/{b_document['id']}/file-url", headers=as_user(w.a_admin)),
        # B's document id under A's workspace path: scoped lookup finds nothing.
        await db_client.get(
            f"/v1/workspaces/{w.a.id}/documents/{b_document['id']}", headers=as_user(w.a_admin)
        ),
        await db_client.get(f"/v1/workspaces/{w.a.id}/documents/nope", headers=as_user(w.a_admin)),
    ]

    assert listing.json()["items"] == []
    assert [response.status_code for response in responses] == [404] * 5
