from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from app.jobs import repository as queue
from app.jobs.models import Job
from app.storage.fake import FakeStorage
from tests.support.pipeline import seed_document, seed_workspaces


async def test_ac5_two_claimers_never_get_same_job(committing_engine: AsyncEngine) -> None:
    seeded = await seed_workspaces(committing_engine)
    storage = FakeStorage()
    await seed_document(seeded, storage, b"%PDF-1")
    await seed_document(seeded, storage, b"%PDF-2")

    # Both claim inside open transactions: SKIP LOCKED makes the second pass the first.
    async with (
        seeded.sessionmaker() as first,
        seeded.sessionmaker() as second,
        first.begin(),
        second.begin(),
    ):
        a = await queue.claim(first, worker_id="a")
        b = await queue.claim(second, worker_id="b")
        async with seeded.sessionmaker() as third, third.begin():
            c = await queue.claim(third, worker_id="c")

    assert a is not None
    assert b is not None
    assert a.id != b.id
    assert c is None


async def test_ac5_expired_lease_is_reclaimed(committing_engine: AsyncEngine) -> None:
    seeded = await seed_workspaces(committing_engine)
    await seed_document(seeded, FakeStorage())
    async with seeded.sessionmaker() as session, session.begin():
        first = await queue.claim(session, worker_id="crashed")
    assert first is not None

    async with seeded.sessionmaker() as session, session.begin():
        assert await queue.claim(session, worker_id="b") is None  # lease still held
        await session.execute(update(Job).values(locked_until=func.now() - timedelta(seconds=1)))
    async with seeded.sessionmaker() as session, session.begin():
        second = await queue.claim(session, worker_id="b")

    assert second is not None
    assert (second.id, second.attempts) == (first.id, 2)


async def test_ac5_stale_worker_cannot_finish_reclaimed_job(committing_engine: AsyncEngine) -> None:
    seeded = await seed_workspaces(committing_engine)
    await seed_document(seeded, FakeStorage())
    async with seeded.sessionmaker() as session, session.begin():
        job = await queue.claim(session, worker_id="slow")
        assert job is not None
        await session.execute(update(Job).values(locked_until=func.now() - timedelta(seconds=1)))
    async with seeded.sessionmaker() as session, session.begin():
        assert await queue.claim(session, worker_id="fast") is not None

    async with seeded.sessionmaker() as session, session.begin():
        stale = await queue.mark_succeeded(session, job.id, worker_id="slow")
        current = await queue.mark_succeeded(session, job.id, worker_id="fast")

    assert (stale, current) == (False, True)


async def test_ac3_retry_later_schedules_the_next_attempt(committing_engine: AsyncEngine) -> None:
    seeded = await seed_workspaces(committing_engine)
    await seed_document(seeded, FakeStorage())
    async with seeded.sessionmaker() as session, session.begin():
        job = await queue.claim(session, worker_id="w")
        assert job is not None
        await queue.retry_later(session, job.id, worker_id="w", delay_seconds=60, error="503")

    async with seeded.sessionmaker() as session:
        row = (await session.scalars(select(Job))).one()
        due_in = await queue.seconds_until_next_due(session)
        assert await queue.claim(session, worker_id="w") is None

    assert (row.status, row.locked_by, row.last_error) == ("queued", None, "503")
    assert due_in is not None
    assert 55 < due_in <= 60


async def test_no_work_means_nothing_due(committing_engine: AsyncEngine) -> None:
    seeded = await seed_workspaces(committing_engine)
    async with seeded.sessionmaker() as session:
        assert await queue.seconds_until_next_due(session) is None
