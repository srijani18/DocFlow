import asyncio

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.auth.verifier import VerifiedClaims
from app.identity import repository, service
from app.identity.models import Membership, User, Workspace
from app.identity.service import provision_or_load

CLAIMS = VerifiedClaims(
    subject="supabase-user-1", email="ada@example.com", display_name="Ada", session_id=None
)


@pytest.fixture
def sessions(committing_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(committing_engine, expire_on_commit=False)


async def _counts(engine: AsyncEngine) -> tuple[int, int, int]:
    async with engine.connect() as connection:
        users = await connection.scalar(select(func.count()).select_from(User))
        workspaces = await connection.scalar(select(func.count()).select_from(Workspace))
        memberships = await connection.scalar(select(func.count()).select_from(Membership))
    return users or 0, workspaces or 0, memberships or 0


async def _provision_in_own_transaction(
    sessions: async_sessionmaker[AsyncSession], claims: VerifiedClaims = CLAIMS
) -> service.CurrentUser:
    async with sessions() as session, session.begin():
        return await provision_or_load(session, claims)


async def test_ac5_first_request_creates_user_workspace_admin_membership(
    db_session: AsyncSession,
) -> None:
    current = await provision_or_load(db_session, CLAIMS)

    user = await db_session.get(User, current.id)
    assert user is not None
    assert (user.auth_subject, user.email, user.display_name) == (
        "supabase-user-1",
        "ada@example.com",
        "Ada",
    )
    memberships = (
        await db_session.scalars(select(Membership).where(Membership.user_id == user.id))
    ).all()
    assert [m.role for m in memberships] == ["admin"]
    workspace = await db_session.get(Workspace, memberships[0].workspace_id)
    assert workspace is not None
    assert (workspace.name, workspace.created_by_user_id) == ("Ada's workspace", user.id)


async def test_ac5_failure_midway_creates_nothing(
    sessions: async_sessionmaker[AsyncSession],
    committing_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("database hiccup after the user insert")

    monkeypatch.setattr(repository, "insert_workspace_with_admin", fail)

    with pytest.raises(RuntimeError):
        await _provision_in_own_transaction(sessions)

    assert await _counts(committing_engine) == (0, 0, 0)


async def test_ac6_repeat_requests_reuse_the_same_user(db_session: AsyncSession) -> None:
    first = await provision_or_load(db_session, CLAIMS)
    second = await provision_or_load(db_session, CLAIMS)

    assert first.id == second.id
    count = await db_session.scalar(select(func.count()).select_from(Workspace))
    assert count == 1


async def test_ac6_concurrent_first_requests_create_one_workspace(
    sessions: async_sessionmaker[AsyncSession], committing_engine: AsyncEngine
) -> None:
    results = await asyncio.gather(*(_provision_in_own_transaction(sessions) for _ in range(10)))

    assert len({result.id for result in results}) == 1
    assert await _counts(committing_engine) == (1, 1, 1)


async def _wait_until_blocked_on_a_lock(engine: AsyncEngine) -> None:
    # Ask Postgres, rather than sleeping: is some backend waiting on a lock right now?
    async with engine.connect() as connection:
        for _ in range(200):
            waiting = await connection.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND wait_event_type = 'Lock'"
                )
            )
            if waiting:
                return
            await asyncio.sleep(0.01)
    raise AssertionError("the second transaction never blocked on the first one's insert")


async def test_ac6_blocked_insert_returns_winner(
    sessions: async_sessionmaker[AsyncSession], committing_engine: AsyncEngine
) -> None:
    async with sessions() as winner_session:
        winner = await provision_or_load(winner_session, CLAIMS)  # inserted, not committed

        loser = asyncio.create_task(_provision_in_own_transaction(sessions))
        await _wait_until_blocked_on_a_lock(committing_engine)
        assert not loser.done()

        await winner_session.commit()
        result = await loser

    assert result.id == winner.id
    assert await _counts(committing_engine) == (1, 1, 1)


async def test_ac7_changed_email_is_updated(db_session: AsyncSession) -> None:
    created = await provision_or_load(db_session, CLAIMS)

    renamed = VerifiedClaims(
        subject=CLAIMS.subject, email="ada@new.example", display_name="Ada L.", session_id=None
    )
    current = await provision_or_load(db_session, renamed)

    user = await db_session.get(User, created.id)
    assert user is not None
    await db_session.refresh(user)
    assert (current.email, user.email) == ("ada@new.example", "ada@new.example")
    assert user.display_name == "Ada L."


async def test_ac8_workspace_name_falls_back_to_email(db_session: AsyncSession) -> None:
    claims = VerifiedClaims(
        subject="s-2", email="grace@example.com", display_name=None, session_id=None
    )

    current = await provision_or_load(db_session, claims)

    name = await db_session.scalar(
        select(Workspace.name).join(Membership).where(Membership.user_id == current.id)
    )
    assert name == "grace's workspace"
