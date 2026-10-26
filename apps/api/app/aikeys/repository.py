"""SQL for workspaces' AI keys. Every function is scoped to one workspace."""

import uuid
from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.aikeys.crypto import Sealed
from app.aikeys.models import WorkspaceAiKey
from app.core.tenancy import WorkspaceScope


async def list_keys(session: AsyncSession, scope: WorkspaceScope) -> list[WorkspaceAiKey]:
    rows = await session.scalars(
        select(WorkspaceAiKey).where(WorkspaceAiKey.workspace_id == scope.workspace_id)
    )
    return list(rows)


async def get_key(
    session: AsyncSession, scope: WorkspaceScope, provider: str
) -> WorkspaceAiKey | None:
    row: WorkspaceAiKey | None = await session.scalar(
        select(WorkspaceAiKey).where(
            WorkspaceAiKey.workspace_id == scope.workspace_id, WorkspaceAiKey.provider == provider
        )
    )
    return row


async def upsert_key(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    provider: str,
    sealed: Sealed,
    last4: str,
    status: str,
    checked_at: datetime,
) -> WorkspaceAiKey:
    values = {
        "ciphertext": sealed.ciphertext,
        "nonce": sealed.nonce,
        "key_version": sealed.key_version,
        "last4": last4,
        "status": status,
        "checked_at": checked_at,
        "updated_by_user_id": scope.user_id,
    }
    statement = (
        insert(WorkspaceAiKey)
        .values(workspace_id=scope.workspace_id, provider=provider, **values)
        .on_conflict_do_update(
            index_elements=[WorkspaceAiKey.workspace_id, WorkspaceAiKey.provider],
            set_={**values, "updated_at": func.now()},
        )
        .returning(WorkspaceAiKey)
        .execution_options(populate_existing=True)
    )
    row: WorkspaceAiKey = (await session.scalars(statement)).one()
    return row


async def set_status(
    session: AsyncSession,
    scope: WorkspaceScope,
    provider: str,
    *,
    status: str,
    checked_at: datetime | None,
) -> None:
    values: dict[str, object] = {"status": status, "updated_at": func.now()}
    if checked_at is not None:
        values["checked_at"] = checked_at
    await session.execute(
        update(WorkspaceAiKey)
        .where(
            WorkspaceAiKey.workspace_id == scope.workspace_id, WorkspaceAiKey.provider == provider
        )
        .values(**values)
    )


async def delete_key(session: AsyncSession, scope: WorkspaceScope, provider: str) -> bool:
    result = await session.execute(
        delete(WorkspaceAiKey)
        .where(
            WorkspaceAiKey.workspace_id == scope.workspace_id, WorkspaceAiKey.provider == provider
        )
        .returning(WorkspaceAiKey.provider)
    )
    return result.first() is not None


async def usable_keys(session: AsyncSession, workspace_id: uuid.UUID) -> list[WorkspaceAiKey]:
    """Keys the gateway may use: everything not marked rejected (F15 AC9)."""
    rows = await session.scalars(
        select(WorkspaceAiKey).where(
            WorkspaceAiKey.workspace_id == workspace_id, WorkspaceAiKey.status != "rejected"
        )
    )
    return list(rows)
