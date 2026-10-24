"""SQL for users, workspaces and memberships. No business rules here (constitution §11)."""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import WorkspaceScope
from app.identity.models import Membership, User, Workspace


@dataclass(frozen=True)
class MembershipRow:
    workspace_id: uuid.UUID
    workspace_name: str
    role: str


async def get_user_by_subject(session: AsyncSession, auth_subject: str) -> User | None:
    # tenant-unscoped: users are global; a person can belong to several workspaces.
    user: User | None = await session.scalar(select(User).where(User.auth_subject == auth_subject))
    return user


async def insert_user_if_absent(
    session: AsyncSession, *, auth_subject: str, email: str | None, display_name: str | None
) -> uuid.UUID | None:
    """Insert the user, or return None if another transaction already did.

    If a concurrent transaction has inserted the same subject but not committed yet,
    Postgres makes this statement wait for it, then reports the conflict (plan §4.3).
    """
    statement = (
        pg_insert(User)
        .values(auth_subject=auth_subject, email=email, display_name=display_name)
        .on_conflict_do_nothing(index_elements=[User.auth_subject])
        .returning(User.id)
    )
    user_id: uuid.UUID | None = await session.scalar(statement)
    return user_id


async def insert_workspace_with_admin(
    session: AsyncSession, *, user_id: uuid.UUID, name: str
) -> uuid.UUID:
    result = await session.execute(
        insert(Workspace).values(name=name, created_by_user_id=user_id).returning(Workspace.id)
    )
    workspace_id: uuid.UUID = result.scalar_one()
    # tenant-unscoped: this creates the tenant and its first member; no scope exists yet.
    await session.execute(
        insert(Membership).values(workspace_id=workspace_id, user_id=user_id, role="admin")
    )
    return workspace_id


async def update_user_profile(
    session: AsyncSession, *, user_id: uuid.UUID, email: str | None, display_name: str | None
) -> None:
    # tenant-unscoped: users are global.
    await session.execute(
        update(User)
        .where(User.id == user_id)
        .values(email=email, display_name=display_name, updated_at=func.now())
    )


async def list_memberships(session: AsyncSession, user_id: uuid.UUID) -> list[MembershipRow]:
    # tenant-unscoped: lists the caller's own memberships across workspaces, filtered by
    # user_id; this is how the caller learns which workspace scopes they may use.
    rows = await session.execute(
        select(Membership.workspace_id, Workspace.name, Membership.role)
        .join(Workspace, Workspace.id == Membership.workspace_id)
        .where(Membership.user_id == user_id)
        .order_by(Membership.created_at, Workspace.name)
    )
    return [MembershipRow(row.workspace_id, row.name, row.role) for row in rows]


async def get_member_role(
    session: AsyncSession, *, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> str | None:
    """The membership check behind every WorkspaceScope. None means "not a member"."""
    role: str | None = await session.scalar(
        select(Membership.role).where(
            Membership.workspace_id == workspace_id, Membership.user_id == user_id
        )
    )
    return role


async def get_workspace(session: AsyncSession, scope: WorkspaceScope) -> Workspace | None:
    workspace: Workspace | None = await session.scalar(
        select(Workspace).where(Workspace.id == scope.workspace_id)
    )
    return workspace


async def update_workspace_name(
    session: AsyncSession, scope: WorkspaceScope, name: str
) -> Workspace | None:
    workspace: Workspace | None = await session.scalar(
        update(Workspace)
        .where(Workspace.id == scope.workspace_id)
        .values(name=name, updated_at=func.now())
        .returning(Workspace)
    )
    return workspace
