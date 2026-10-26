from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine

from app.aikeys import service
from app.aikeys.crypto import KeyBox
from app.core.tenancy import WorkspaceScope
from app.llm.gateway import Credentials
from app.llm.types import CredentialRejectedError
from app.pipeline.runner import Pipeline
from app.pipeline.steps.classify import ClassifyStep
from app.pipeline.steps.extract import ExtractStep
from app.storage.fake import FakeStorage
from app.worker.loop import Worker
from tests.conftest import TEST_BYOK_MASTER_KEYS
from tests.integration.aikeys.conftest import FakeChecker
from tests.support.clock import FrozenClock
from tests.support.llm import StaticCredentials, answers, fake_gateway
from tests.support.pipeline import (
    Recorder,
    Seeded,
    document_row,
    jobs_for,
    llm_calls_for,
    seed_document,
    seed_workspaces,
)

KEYBOX = KeyBox.from_setting(TEST_BYOK_MASTER_KEYS)


async def store(seeded: Seeded, scope: WorkspaceScope, key: str) -> None:
    checker = FakeChecker(clock=FrozenClock())
    async with seeded.sessionmaker() as session, session.begin():
        await service.save_key(
            session,
            scope,
            keybox=KEYBOX,
            checker=checker,  # type: ignore[arg-type]
            provider="gemini",
            api_key=key,
        )


def b_scope(seeded: Seeded) -> WorkspaceScope:
    w = seeded.workspaces
    return WorkspaceScope(workspace_id=w.b.id, user_id=w.b_admin.id, role="admin")


async def test_ac6_calls_use_workspace_key(committing_engine: AsyncEngine) -> None:
    seeded = await seed_workspaces(committing_engine)
    await store(seeded, seeded.scope, "key-for-workspace-a")
    await store(seeded, b_scope(seeded), "key-for-workspace-b")
    credentials = service.WorkspaceCredentials(sessionmaker=seeded.sessionmaker, keybox=KEYBOX)

    keys_a = await credentials.keys_for(seeded.workspaces.a.id)
    keys_b = await credentials.keys_for(seeded.workspaces.b.id)

    assert keys_a == {"gemini": "key-for-workspace-a"}
    assert keys_b == {"gemini": "key-for-workspace-b"}


async def test_ac9_rejected_key_is_not_used_again(committing_engine: AsyncEngine) -> None:
    seeded = await seed_workspaces(committing_engine)
    await store(seeded, seeded.scope, "key-for-workspace-a")
    credentials = service.WorkspaceCredentials(sessionmaker=seeded.sessionmaker, keybox=KEYBOX)

    await credentials.mark_rejected(seeded.workspaces.a.id, "gemini")

    assert await credentials.keys_for(seeded.workspaces.a.id) == {}


async def test_without_master_key_no_key_is_usable(committing_engine: AsyncEngine) -> None:
    seeded = await seed_workspaces(committing_engine)
    await store(seeded, seeded.scope, "key-for-workspace-a")
    credentials = service.WorkspaceCredentials(sessionmaker=seeded.sessionmaker, keybox=None)

    assert await credentials.keys_for(seeded.workspaces.a.id) == {}


def worker_with(
    seeded: Seeded, storage: FakeStorage, credentials: Credentials, *replies: Any
) -> tuple[Worker, Any]:
    gateway, provider = fake_gateway(seeded.sessionmaker, answers(*replies), credentials)
    pipeline = Pipeline(
        sessionmaker=seeded.sessionmaker,
        storage=storage,
        publish=Recorder().publish,
        classify=ClassifyStep(gateway, prompt_version="classify/v1"),
        extract=ExtractStep(gateway, prompt_version="extract/v1"),
    )
    return Worker(
        sessionmaker=seeded.sessionmaker, pipeline=pipeline, events=Recorder(), worker_id="t"
    ), provider


async def test_ac7_no_key_fails_permanently_with_code(committing_engine: AsyncEngine) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    document_id = await seed_document(seeded, storage)
    credentials = StaticCredentials(without={seeded.workspaces.a.id})
    worker, provider = worker_with(
        seeded, storage, credentials, {"doc_type": "invoice", "confidence": 0.9}
    )

    await worker.drain()

    document = await document_row(seeded, document_id)
    assert (document.status, document.failure_reason, document.failure_code) == (
        "FAILED",
        "No AI provider key connected",
        "no_ai_key",
    )
    [job] = await jobs_for(seeded, document_id)
    assert (job.status, job.attempts) == ("dead", 1)
    assert provider.requests == []  # nothing was sent anywhere


async def test_ac6_another_workspaces_key_is_never_used(committing_engine: AsyncEngine) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    document_id = await seed_document(seeded, storage)  # in workspace A
    await store(seeded, b_scope(seeded), "key-for-workspace-b")  # only B has a key
    credentials = service.WorkspaceCredentials(sessionmaker=seeded.sessionmaker, keybox=KEYBOX)
    worker, provider = worker_with(
        seeded, storage, credentials, {"doc_type": "invoice", "confidence": 0.9}
    )

    await worker.drain()

    assert (await document_row(seeded, document_id)).failure_code == "no_ai_key"
    assert provider.requests == []


async def test_ac6_real_credentials_send_the_documents_workspace_key(
    committing_engine: AsyncEngine,
) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    await seed_document(seeded, storage)
    await store(seeded, seeded.scope, "key-for-workspace-a")
    await store(seeded, b_scope(seeded), "key-for-workspace-b")
    credentials = service.WorkspaceCredentials(sessionmaker=seeded.sessionmaker, keybox=KEYBOX)
    gateway_keys = {"fake": (await credentials.keys_for(seeded.workspaces.a.id))["gemini"]}
    worker, provider = worker_with(
        seeded,
        storage,
        StaticCredentials(keys=gateway_keys),
        {"doc_type": "other", "confidence": 0.9},
    )

    await worker.drain()

    assert [request.api_key for request in provider.requests] == ["key-for-workspace-a"]


async def test_ac9_rejected_key_marked_and_document_fails_with_code(
    committing_engine: AsyncEngine,
) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    document_id = await seed_document(seeded, storage)
    credentials = StaticCredentials()
    worker, _ = worker_with(
        seeded,
        storage,
        credentials,
        CredentialRejectedError("Gemini rejected the key (403)", provider="fake"),
    )

    await worker.drain()

    document = await document_row(seeded, document_id)
    assert (document.status, document.failure_code) == ("FAILED", "key_rejected")
    assert credentials.rejected == [(seeded.workspaces.a.id, "fake")]
    [call] = await llm_calls_for(seeded, document_id)
    assert (call.outcome, call.error_type) == ("error", "CredentialRejectedError")
