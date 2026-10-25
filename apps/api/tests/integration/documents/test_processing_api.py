import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import WorkspaceScope
from app.documents import service
from app.documents.models import Upload
from app.jobs.models import Job
from app.storage.fake import FakeStorage
from tests.support.documents import as_user, upload_document
from tests.support.identity import TwoWorkspaces
from tests.support.pipeline import Recorder


async def fail_document(session: AsyncSession, w: TwoWorkspaces, document_id: str) -> None:
    scope = WorkspaceScope(workspace_id=w.a.id, user_id=w.a_admin.id, role="admin")
    event = await service.fail(
        session, scope, uuid.UUID(document_id), reason="Boom", job_id=None, detail=None
    )
    assert event is not None
    await session.commit()


async def test_ac1_complete_queues_job_and_wakes_worker(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
    wakeups: list[str],
    published: Recorder,
) -> None:
    w = two_workspaces
    document = await upload_document(db_client, fake_storage, w.a.id, w.a_admin)

    jobs = list(await db_session.scalars(select(Job)))
    assert [(str(job.document_id), job.status) for job in jobs] == [(document["id"], "queued")]
    assert jobs[0].idempotency_key == f"process_document:{document['id']}:1"
    assert wakeups == ["wake"]
    assert published.statuses == ["UPLOADED"]
    assert document["status_changed_at"]


async def test_duplicate_completion_queues_nothing_more(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
    wakeups: list[str],
) -> None:
    w = two_workspaces
    await upload_document(db_client, fake_storage, w.a.id, w.a_admin)
    upload_id = (await db_session.scalars(select(Upload.id))).one()

    # Completing the same upload again (F2 AC5) must not add a job or wake anyone.
    again = await db_client.post(
        f"/v1/workspaces/{w.a.id}/uploads/{upload_id}/complete", headers=as_user(w.a_admin)
    )

    assert again.status_code == 200
    assert len(list(await db_session.scalars(select(Job)))) == 1
    assert wakeups == ["wake"]


@pytest.mark.parametrize("member", ["a_admin", "a_reviewer"])
async def test_ac8_retry_failed_document_requeues_with_fresh_attempts(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
    wakeups: list[str],
    published: Recorder,
    member: str,
) -> None:
    w = two_workspaces
    document = await upload_document(db_client, fake_storage, w.a.id, w.a_admin)
    await fail_document(db_session, w, document["id"])

    response = await db_client.post(
        f"/v1/workspaces/{w.a.id}/documents/{document['id']}/retry",
        headers=as_user(getattr(w, member)),
    )

    assert response.status_code == 202
    assert (response.json()["status"], response.json()["failure_reason"]) == ("UPLOADED", None)
    jobs = list(await db_session.scalars(select(Job).order_by(Job.created_at)))
    assert [job.idempotency_key.rsplit(":", 1)[1] for job in jobs] == ["1", "2"]
    assert (jobs[1].status, jobs[1].attempts) == ("queued", 0)
    assert wakeups == ["wake", "wake"]
    assert published.statuses[-1] == "UPLOADED"


async def test_ac8_retry_non_failed_is_409(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces, fake_storage: FakeStorage
) -> None:
    w = two_workspaces
    document = await upload_document(db_client, fake_storage, w.a.id, w.a_admin)

    response = await db_client.post(
        f"/v1/workspaces/{w.a.id}/documents/{document['id']}/retry", headers=as_user(w.a_admin)
    )

    assert response.status_code == 409
    assert response.json()["type"].endswith("/not-retryable")


async def test_ac8_double_retry_one_job(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
) -> None:
    w = two_workspaces
    document = await upload_document(db_client, fake_storage, w.a.id, w.a_admin)
    await fail_document(db_session, w, document["id"])
    url = f"/v1/workspaces/{w.a.id}/documents/{document['id']}/retry"

    first = await db_client.post(url, headers=as_user(w.a_admin))
    second = await db_client.post(url, headers=as_user(w.a_admin))

    assert (first.status_code, second.status_code) == (202, 409)
    assert len(list(await db_session.scalars(select(Job)))) == 2


async def test_ac10_retry_other_workspace_404(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
) -> None:
    w = two_workspaces
    document = await upload_document(db_client, fake_storage, w.a.id, w.a_admin)
    await fail_document(db_session, w, document["id"])

    via_b = await db_client.post(
        f"/v1/workspaces/{w.b.id}/documents/{document['id']}/retry", headers=as_user(w.b_admin)
    )
    a_doc_under_b = await db_client.post(
        f"/v1/workspaces/{w.b.id}/documents/{document['id']}/retry", headers=as_user(w.a_admin)
    )

    assert (via_b.status_code, a_doc_under_b.status_code) == (404, 404)


async def test_ac10_event_stream_requires_membership(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces
) -> None:
    w = two_workspaces
    other = await db_client.get(f"/v1/workspaces/{w.b.id}/events", headers=as_user(w.a_admin))
    anonymous = await db_client.get(f"/v1/workspaces/{w.a.id}/events")

    assert (other.status_code, anonymous.status_code) == (404, 401)
