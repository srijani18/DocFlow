"""Workspace access tokens: create, list, revoke and verify (F12 AC1-AC3).

A token is `dfw_` and 32 random bytes. Only its sha256 is stored, so a database copy can't
be used to call the MCP server. It acts as its creator, read-only, in one workspace, and
only while it is unexpired, unrevoked and the creator is still a member.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.tenancy import WorkspaceScope
from app.identity.models import Membership, User
from app.mcp.models import ApiToken

TOKEN_PREFIX = "dfw_"  # noqa: S105  # a public marker that scanners can match, not a secret
SHOWN_CHARACTERS = 8
ExpiryDays = Literal[30, 90, 365]
# last_used_at is shown in days and hours; a write per call would be wasted.
LAST_USED_RESOLUTION = timedelta(minutes=1)


def new_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class TokenRow:
    token: ApiToken
    creator_email: str | None
    active: bool


@dataclass(frozen=True)
class VerifiedToken:
    token_id: uuid.UUID
    scope: WorkspaceScope


async def create_token(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    name: str,
    expires_in_days: ExpiryDays,
    now: datetime,
) -> tuple[ApiToken, str]:
    """The new row and the token itself, which is never available again (AC1)."""
    token = new_token()
    row = ApiToken(
        workspace_id=scope.workspace_id,
        user_id=scope.user_id,
        name=name,
        prefix=token[:SHOWN_CHARACTERS],
        token_hash=hash_token(token),
        created_at=now,
        expires_at=now + timedelta(days=expires_in_days),
    )
    session.add(row)
    await session.flush()
    return row, token


async def list_tokens(
    session: AsyncSession, scope: WorkspaceScope, *, now: datetime
) -> list[TokenRow]:
    """A member's own tokens; every token of the workspace for an admin (AC3)."""
    statement = (
        select(ApiToken, User.email, Membership.user_id)
        .join(User, User.id == ApiToken.user_id)
        .outerjoin(
            Membership,
            and_(
                Membership.workspace_id == ApiToken.workspace_id,
                Membership.user_id == ApiToken.user_id,
            ),
        )
        .where(ApiToken.workspace_id == scope.workspace_id)
        .order_by(ApiToken.created_at.desc(), ApiToken.id)
    )
    if scope.role != "admin":
        statement = statement.where(ApiToken.user_id == scope.user_id)
    return [
        TokenRow(
            token=token,
            creator_email=email,
            active=member is not None and token.revoked_at is None and token.expires_at > now,
        )
        for token, email, member in await session.execute(statement)
    ]


async def revoke_token(
    session: AsyncSession, scope: WorkspaceScope, token_id: str, *, now: datetime
) -> None:
    """Revoke the caller's own token, or any token as an admin. Revoking twice is fine."""
    try:
        parsed = uuid.UUID(token_id)
    except ValueError:
        raise NotFoundError() from None
    statement = select(ApiToken).where(
        ApiToken.workspace_id == scope.workspace_id, ApiToken.id == parsed
    )
    if scope.role != "admin":
        statement = statement.where(ApiToken.user_id == scope.user_id)
    token = await session.scalar(statement)
    if token is None:
        raise NotFoundError()
    if token.revoked_at is None:
        token.revoked_at = now
        await session.flush()


async def verify_token(session: AsyncSession, token: str, *, now: datetime) -> VerifiedToken | None:
    """The scope a presented token acts in, or None for any reason it can't (AC2, AC4)."""
    if not token.startswith(TOKEN_PREFIX):
        return None
    # Looked up by its hash across workspaces: the token is what names the workspace.
    row = (
        await session.execute(
            select(ApiToken, Membership.role)
            .join(
                Membership,
                and_(
                    Membership.workspace_id == ApiToken.workspace_id,
                    Membership.user_id == ApiToken.user_id,
                ),
            )
            .where(
                ApiToken.token_hash == hash_token(token),
                ApiToken.revoked_at.is_(None),
                ApiToken.expires_at > now,
            )
        )
    ).one_or_none()
    if row is None:
        return None
    api_token, role = row
    if api_token.last_used_at is None or now - api_token.last_used_at >= LAST_USED_RESOLUTION:
        await session.execute(
            update(ApiToken).where(ApiToken.id == api_token.id).values(last_used_at=now)
        )
    return VerifiedToken(
        token_id=api_token.id,
        scope=WorkspaceScope(
            workspace_id=api_token.workspace_id, user_id=api_token.user_id, role=role
        ),
    )
