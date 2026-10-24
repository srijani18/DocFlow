"""Identity use cases (F1 plan §4.3). Framework-free: called by FastAPI dependencies."""

import unicodedata
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.verifier import VerifiedClaims
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.core.tenancy import WorkspaceScope
from app.identity import repository
from app.identity.models import WORKSPACE_NAME_MAX_LENGTH, Workspace
from app.identity.repository import MembershipRow

log = get_logger(__name__)

FALLBACK_WORKSPACE_NAME = "My workspace"


@dataclass(frozen=True)
class CurrentUser:
    id: uuid.UUID
    auth_subject: str
    email: str | None
    display_name: str | None


def default_workspace_name(*, display_name: str | None, email: str | None) -> str:
    """AC8: display name, else the email's local part, else a fallback; at most 80 chars."""
    base = (display_name or "").strip()
    if not base and email:
        base = email.split("@", 1)[0].strip()
    if not base:
        return FALLBACK_WORKSPACE_NAME
    # NFC first, so cutting never separates a letter from its combining accent.
    name = unicodedata.normalize("NFC", f"{base}'s workspace")
    return name[:WORKSPACE_NAME_MAX_LENGTH].rstrip()


async def provision_or_load(session: AsyncSession, claims: VerifiedClaims) -> CurrentUser:
    """Return the caller's user, creating user + personal workspace + admin membership on
    first sight, exactly once even under concurrent first requests (AC5, AC6).

    Runs in the caller's transaction, so the three rows commit together or not at all.
    """
    user = await repository.get_user_by_subject(session, claims.subject)
    if user is None:
        new_user_id = await repository.insert_user_if_absent(
            session,
            auth_subject=claims.subject,
            email=claims.email,
            display_name=claims.display_name,
        )
        if new_user_id is not None:
            await repository.insert_workspace_with_admin(
                session,
                user_id=new_user_id,
                name=default_workspace_name(display_name=claims.display_name, email=claims.email),
            )
            log.info("user_provisioned", user_id=str(new_user_id))
            return CurrentUser(new_user_id, claims.subject, claims.email, claims.display_name)
        # A concurrent request won the insert and has committed by now.
        user = await repository.get_user_by_subject(session, claims.subject)
        if user is None:
            raise RuntimeError("user row missing after a conflicting insert")

    display_name = claims.display_name if claims.display_name is not None else user.display_name
    if (user.email, user.display_name) != (claims.email, display_name):
        await repository.update_user_profile(
            session, user_id=user.id, email=claims.email, display_name=display_name
        )
    return CurrentUser(user.id, user.auth_subject, claims.email, display_name)


async def list_memberships(session: AsyncSession, user_id: uuid.UUID) -> list[MembershipRow]:
    return await repository.list_memberships(session, user_id)


async def get_member_role(
    session: AsyncSession, *, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> str | None:
    return await repository.get_member_role(session, workspace_id=workspace_id, user_id=user_id)


async def get_workspace(session: AsyncSession, scope: WorkspaceScope) -> Workspace:
    workspace = await repository.get_workspace(session, scope)
    if workspace is None:  # deleted between the membership check and now
        raise NotFoundError()
    return workspace


async def rename_workspace(session: AsyncSession, scope: WorkspaceScope, name: str) -> Workspace:
    """AC16. `name` is already trimmed and length-checked by the API model; the database
    CHECK constraint enforces the same rule as a backstop."""
    workspace = await repository.update_workspace_name(session, scope, name)
    if workspace is None:
        raise NotFoundError()
    log.info("workspace_renamed")
    return workspace
