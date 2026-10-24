"""The rollback-per-test fixture really isolates tests (P0-T9 done-when).

The two tests run in file order: the first writes, the second must not see it.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def test_writer_creates_and_commits_data(db_session: AsyncSession) -> None:
    await db_session.execute(text("CREATE TABLE _isolation_probe (v int)"))
    await db_session.execute(text("INSERT INTO _isolation_probe VALUES (1)"))
    await db_session.commit()  # only releases a savepoint inside the test transaction

    count = await db_session.scalar(text("SELECT count(*) FROM _isolation_probe"))
    assert count == 1


async def test_reader_does_not_see_previous_test_data(db_session: AsyncSession) -> None:
    exists = await db_session.scalar(text("SELECT to_regclass('_isolation_probe') IS NOT NULL"))
    assert exists is False
