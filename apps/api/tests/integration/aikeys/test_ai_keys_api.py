import uuid

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.aikeys.checks import CheckResult
from app.aikeys.models import WorkspaceAiKey
from app.core.tenancy import WorkspaceScope
from app.documents import service as documents
from app.jobs.models import Job
from app.storage.fake import FakeStorage
from tests.integration.aikeys.conftest import FakeChecker
from tests.support.documents import as_user, upload_document
from tests.support.identity import TwoWorkspaces, UserRef

KEY = "AIzaSy-workspace-a-secret-9f3k"


def url(w: TwoWorkspaces, provider: str = "gemini", workspace: str = "a") -> str:
    return f"/v1/workspaces/{getattr(w, workspace).id}/ai-keys/{provider}"


async def save(
    client: httpx.AsyncClient, w: TwoWorkspaces, user: UserRef, key: str = KEY
) -> httpx.Response:
    return await client.put(url(w), json={"api_key": key}, headers=as_user(user))


async def statuses(
    client: httpx.AsyncClient, w: TwoWorkspaces, user: UserRef
) -> dict[str, dict[str, object]]:
    response = await client.get(f"/v1/workspaces/{w.a.id}/ai-keys", headers=as_user(user))
    assert response.status_code == 200
    return {item["provider"]: item for item in response.json()}


async def test_ac1_valid_key_saved_masked_and_encrypted(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    key_checker: FakeChecker,
    db_session: AsyncSession,
) -> None:
    w = two_workspaces
    response = await save(db_client, w, w.a_admin)

    assert response.status_code == 200
    body = response.json()
    assert (body["provider"], body["connected"], body["last4"], body["status"]) == (
        "gemini",
        True,
        "9f3k",
        "ok",
    )
    assert body["checked_at"]
    assert key_checker.checked == [("gemini", KEY)]
    row = (await db_session.scalars(select(WorkspaceAiKey))).one()
    assert KEY.encode() not in row.ciphertext
    assert row.key_version == 1


async def test_ac1_invalid_key_rejected_nothing_stored(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces, key_checker: FakeChecker
) -> None:
    w = two_workspaces
    key_checker.result = CheckResult.REJECTED

    response = await save(db_client, w, w.a_admin)

    assert response.status_code == 422
    assert response.json()["type"].endswith("/invalid-api-key")
    assert KEY not in response.text
    assert (await statuses(db_client, w, w.a_admin))["gemini"]["connected"] is False


async def test_provider_unreachable_during_check_stores_nothing(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces, key_checker: FakeChecker
) -> None:
    w = two_workspaces
    key_checker.result = CheckResult.UNAVAILABLE

    response = await save(db_client, w, w.a_admin)

    assert response.status_code == 503
    assert response.headers["retry-after"]
    assert (await statuses(db_client, w, w.a_admin))["gemini"]["connected"] is False


async def test_ac2_replace_and_remove(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces
) -> None:
    w = two_workspaces
    await save(db_client, w, w.a_admin)
    replaced = await save(db_client, w, w.a_admin, key="AIzaSy-replacement-zzzz")
    removed = await db_client.delete(url(w), headers=as_user(w.a_admin))
    removed_again = await db_client.delete(url(w), headers=as_user(w.a_admin))

    assert replaced.json()["last4"] == "zzzz"
    assert (removed.status_code, removed_again.status_code) == (204, 404)
    assert (await statuses(db_client, w, w.a_admin))["gemini"]["connected"] is False


async def test_ac3_reviewer_sees_status_cannot_manage(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces
) -> None:
    w = two_workspaces
    await save(db_client, w, w.a_admin)

    seen = await statuses(db_client, w, w.a_reviewer)
    attempts = [
        await save(db_client, w, w.a_reviewer),
        await db_client.delete(url(w), headers=as_user(w.a_reviewer)),
        await db_client.post(f"{url(w)}/test", headers=as_user(w.a_reviewer)),
    ]

    assert (seen["gemini"]["connected"], seen["gemini"]["last4"]) == (True, "9f3k")
    assert set(seen) == {"gemini", "groq", "openrouter"}
    assert [response.status_code for response in attempts] == [403, 403, 403]


async def test_ac4_key_never_in_responses_or_logs(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    capsys: pytest.CaptureFixture[str],
) -> None:
    w = two_workspaces
    responses = [
        await save(db_client, w, w.a_admin),
        await db_client.get(f"/v1/workspaces/{w.a.id}/ai-keys", headers=as_user(w.a_admin)),
        await db_client.post(f"{url(w)}/test", headers=as_user(w.a_admin)),
    ]

    captured = capsys.readouterr()
    assert all(KEY not in response.text for response in responses)
    assert KEY not in captured.out + captured.err


async def test_ac5_test_updates_status(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    key_checker: FakeChecker,
) -> None:
    w = two_workspaces
    await save(db_client, w, w.a_admin)
    key_checker.result = CheckResult.REJECTED
    key_checker.clock.advance(hours=1)

    response = await db_client.post(f"{url(w)}/test", headers=as_user(w.a_admin))

    assert response.json()["status"] == "rejected"
    assert key_checker.checked[-1] == ("gemini", KEY)  # the stored key, decrypted


async def test_other_workspace_and_unknown_provider_404(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces
) -> None:
    w = two_workspaces
    responses = [
        await db_client.put(
            url(w, workspace="b"), json={"api_key": KEY}, headers=as_user(w.a_admin)
        ),
        await db_client.get(f"/v1/workspaces/{w.b.id}/ai-keys", headers=as_user(w.a_admin)),
        await db_client.put(
            url(w, provider="openai"), json={"api_key": KEY}, headers=as_user(w.a_admin)
        ),
    ]

    assert [response.status_code for response in responses] == [404, 404, 404]


async def test_ac8_connecting_key_requeues_no_key_documents(
    db_client: httpx.AsyncClient,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
    db_session: AsyncSession,
    wakeups: list[str],
) -> None:
    w = two_workspaces
    scope = WorkspaceScope(workspace_id=w.a.id, user_id=w.a_admin.id, role="admin")
    waiting = await upload_document(db_client, fake_storage, w.a.id, w.a_admin, data=b"%PDF-1")
    other = await upload_document(db_client, fake_storage, w.a.id, w.a_admin, data=b"%PDF-2")
    await documents.fail(
        db_session,
        scope,
        uuid.UUID(waiting["id"]),
        reason="No AI provider key connected",
        job_id=None,
        detail=None,
        code="no_ai_key",
    )
    await documents.fail(
        db_session,
        scope,
        uuid.UUID(other["id"]),
        reason="File integrity check failed",
        job_id=None,
        detail=None,
        code=None,
    )
    await db_session.commit()
    wakeups.clear()

    await save(db_client, w, w.a_admin)

    base = f"/v1/workspaces/{w.a.id}/documents"
    requeued = (await db_client.get(f"{base}/{waiting['id']}", headers=as_user(w.a_admin))).json()
    untouched = (await db_client.get(f"{base}/{other['id']}", headers=as_user(w.a_admin))).json()
    assert (requeued["status"], requeued["failure_code"]) == ("UPLOADED", None)
    assert (untouched["status"], untouched["failure_code"]) == ("FAILED", None)
    jobs = list(
        await db_session.scalars(select(Job).where(Job.document_id == uuid.UUID(waiting["id"])))
    )
    assert len(jobs) == 2
    assert wakeups == ["wake"]


async def test_ac10_db_dump_has_no_plaintext(
    db_client: httpx.AsyncClient, two_workspaces: TwoWorkspaces, db_session: AsyncSession
) -> None:
    w = two_workspaces
    await save(db_client, w, w.a_admin)

    dump = await db_session.scalar(
        text("SELECT string_agg(t::text, ' ') FROM docflow.workspace_ai_keys t")
    )

    assert dump is not None
    assert KEY not in dump
    assert KEY.encode().hex() not in dump
