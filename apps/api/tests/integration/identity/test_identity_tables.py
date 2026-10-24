"""Database-level guarantees behind F1 (plan §3): the database rejects bad data even if
application code has a bug."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.support.identity import TwoWorkspaces


async def test_auth_subject_is_unique(
    db_session: AsyncSession, two_workspaces: TwoWorkspaces
) -> None:
    with pytest.raises(IntegrityError, match="uq_users_auth_subject"):
        await db_session.execute(
            text("INSERT INTO users (auth_subject) VALUES (:sub)"),
            {"sub": two_workspaces.a_admin.auth_subject},
        )


@pytest.mark.parametrize("name", ["", "x" * 81])
async def test_workspace_name_length_is_enforced(
    db_session: AsyncSession, two_workspaces: TwoWorkspaces, name: str
) -> None:
    with pytest.raises(IntegrityError, match="ck_workspaces_name_length"):
        await db_session.execute(
            text("UPDATE workspaces SET name = :name WHERE id = :id"),
            {"name": name, "id": two_workspaces.a.id},
        )


async def test_membership_role_is_restricted(
    db_session: AsyncSession, two_workspaces: TwoWorkspaces
) -> None:
    with pytest.raises(IntegrityError, match="ck_memberships_role"):
        await db_session.execute(
            text("INSERT INTO memberships (workspace_id, user_id, role) VALUES (:w, :u, 'owner')"),
            {"w": two_workspaces.b.id, "u": two_workspaces.a_admin.id},
        )


async def test_two_workspaces_fixture_shape(two_workspaces: TwoWorkspaces) -> None:
    roles = {(m.workspace_id, m.user_id): m.role for m in two_workspaces.memberships}

    assert roles == {
        (two_workspaces.a.id, two_workspaces.a_admin.id): "admin",
        (two_workspaces.a.id, two_workspaces.a_reviewer.id): "reviewer",
        (two_workspaces.b.id, two_workspaces.b_admin.id): "admin",
    }
