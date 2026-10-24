"""Test data for identity and workspace isolation (F1 plan §10).

`two_workspaces` is the standard isolation fixture for every feature: workspace A has an
admin and a reviewer, and workspace B has an admin who must never see A's data.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.models import Membership, User, Workspace


@dataclass(frozen=True)
class UserRef:
    id: uuid.UUID
    auth_subject: str
    email: str | None


@dataclass(frozen=True)
class WorkspaceRef:
    id: uuid.UUID
    name: str


@dataclass(frozen=True)
class MembershipRef:
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    role: str


@dataclass(frozen=True)
class TwoWorkspaces:
    """Plain values, not ORM objects: a request that rolls back expires the session's
    objects, and tests must keep working after that."""

    a: WorkspaceRef
    b: WorkspaceRef
    a_admin: UserRef
    a_reviewer: UserRef
    b_admin: UserRef
    memberships: tuple[MembershipRef, ...]


async def create_user(session: AsyncSession, *, email: str | None = None) -> User:
    user = User(auth_subject=str(uuid.uuid4()), email=email, display_name=None)
    session.add(user)
    await session.flush()
    return user


async def create_workspace(session: AsyncSession, *, name: str, created_by: User) -> Workspace:
    workspace = Workspace(name=name, created_by_user_id=created_by.id)
    session.add(workspace)
    await session.flush()
    return workspace


async def add_member(
    session: AsyncSession, workspace: Workspace | WorkspaceRef, user: User | UserRef, role: str
) -> Membership:
    membership = Membership(workspace_id=workspace.id, user_id=user.id, role=role)
    session.add(membership)
    await session.flush()
    return membership


async def make_two_workspaces(session: AsyncSession) -> TwoWorkspaces:
    a_admin = await create_user(session, email="a-admin@example.com")
    a_reviewer = await create_user(session, email="a-reviewer@example.com")
    b_admin = await create_user(session, email="b-admin@example.com")
    a = await create_workspace(session, name="Workspace A", created_by=a_admin)
    b = await create_workspace(session, name="Workspace B", created_by=b_admin)
    memberships = (
        await add_member(session, a, a_admin, "admin"),
        await add_member(session, a, a_reviewer, "reviewer"),
        await add_member(session, b, b_admin, "admin"),
    )
    return TwoWorkspaces(
        a=WorkspaceRef(a.id, a.name),
        b=WorkspaceRef(b.id, b.name),
        a_admin=_user_ref(a_admin),
        a_reviewer=_user_ref(a_reviewer),
        b_admin=_user_ref(b_admin),
        memberships=tuple(MembershipRef(m.workspace_id, m.user_id, m.role) for m in memberships),
    )


def _user_ref(user: User) -> UserRef:
    return UserRef(user.id, user.auth_subject, user.email)
