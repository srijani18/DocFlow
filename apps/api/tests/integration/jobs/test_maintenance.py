"""F14 AC11: files of abandoned uploads are deleted; documents' files never are."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.documents.models import Upload
from app.documents.service import upload_path
from app.idempotency.models import IdempotencyKey
from app.storage.fake import FakeStorage
from app.worker.maintenance import Maintenance, Swept
from tests.support.pipeline import Seeded, seed_workspaces


async def add_upload(
    seeded: Seeded, storage: FakeStorage, *, expired_ago: timedelta, completed: bool = False
) -> uuid.UUID:
    async with seeded.sessionmaker() as session, session.begin():
        upload = Upload(
            workspace_id=seeded.scope.workspace_id,
            created_by_user_id=seeded.scope.user_id,
            filename="scan.pdf",
            content_type="application/pdf",
            size_bytes=10,
            sha256=uuid.uuid4().hex,
            expires_at=datetime.now(UTC) - expired_ago,
            document_id=uuid.uuid4() if completed else None,
        )
        session.add(upload)
        await session.flush()
        upload_id = upload.id
    storage.put(upload_path(seeded.scope.workspace_id, upload_id), b"%PDF")
    return upload_id


async def test_ac11_abandoned_files_are_deleted_and_documents_kept(
    committing_engine: AsyncEngine,
) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    document = await add_upload(seeded, storage, expired_ago=timedelta(days=30), completed=True)
    abandoned = await add_upload(seeded, storage, expired_ago=timedelta(hours=2))
    recent = await add_upload(seeded, storage, expired_ago=timedelta(minutes=30))
    ancient = await add_upload(seeded, storage, expired_ago=timedelta(days=8))
    async with seeded.sessionmaker() as session, session.begin():
        for age in (timedelta(hours=25), timedelta(hours=1)):
            session.add(
                IdempotencyKey(
                    workspace_id=seeded.scope.workspace_id,
                    user_id=seeded.scope.user_id,
                    key=str(age),
                    request_hash="h",
                    created_at=datetime.now(UTC) - age,
                )
            )
    maintenance = Maintenance(sessionmaker=seeded.sessionmaker, storage=storage)

    swept = await maintenance.run()
    again = await maintenance.run()

    workspace = seeded.scope.workspace_id
    assert set(storage.objects) == {
        upload_path(workspace, document),
        upload_path(workspace, recent),
    }
    assert swept == Swept(files_deleted=2, uploads_deleted=1, idempotency_keys_deleted=1)
    assert again == Swept(0, 0, 0)
    async with seeded.sessionmaker() as session:
        remaining = {row.id: row.cleaned_at for row in await session.scalars(select(Upload))}
        keys = list(await session.scalars(select(IdempotencyKey.key)))
    assert set(remaining) == {document, abandoned, recent}
    assert ancient not in remaining  # its row went after 7 days
    assert remaining[abandoned] is not None
    assert remaining[document] is None
    assert keys == [str(timedelta(hours=1))]


async def test_ac11_runs_at_most_once_an_hour(committing_engine: AsyncEngine) -> None:
    seeded, storage = await seed_workspaces(committing_engine), FakeStorage()
    now = [0.0]
    maintenance = Maintenance(
        sessionmaker=seeded.sessionmaker, storage=storage, clock=lambda: now[0]
    )

    first = await maintenance.run_if_due()
    now[0] = 1800
    skipped = await maintenance.run_if_due()
    now[0] = 3600
    second = await maintenance.run_if_due()

    assert first is not None
    assert skipped is None
    assert second is not None
