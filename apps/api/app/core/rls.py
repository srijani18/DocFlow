"""Row-level security from the application side (F14 plan §2, ADR-0009).

Every transaction declares whose data it may touch, at its start, from:

1. the session, if it is explicitly a **system** session (`app.core.rls_system`);
2. otherwise the **workspace this task acts for** (`acting_for`, `bind_workspace`): the
   transaction runs as `docflow_app` with `docflow.workspace_id` set, so Postgres returns and
   accepts only that workspace's rows;
3. otherwise the session maker's default: a system session maker (operator tools, tests'
   seeding) runs as the owner;
4. otherwise **nothing**: `docflow_app` with no workspace sees no tenant rows (fail closed).

Settings are `SET LOCAL`: they end with the transaction, so a pooled connection never
carries one request's workspace into another.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any, Literal

from sqlalchemy import Connection, Engine, event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, SessionTransaction

APP_ROLE = "docflow_app"
SYSTEM: Literal["system"] = "system"
# session.info keys
EXPLICIT = "docflow_rls"
DEFAULT = "docflow_rls_default"
# connection.info key: this transaction switched role, so a system transaction must switch back
_SWITCHED = "docflow_rls_switched"

_TENANT_SQL = (
    "SELECT set_config('role', %(role)s, true), set_config('docflow.workspace_id', %(ws)s, true)"
)
_RESET_SQL = "SELECT set_config('role', 'none', true), set_config('docflow.workspace_id', '', true)"

_workspace: ContextVar[uuid.UUID | None] = ContextVar("docflow_workspace", default=None)

Mode = uuid.UUID | None | Literal["system"]


@contextmanager
def acting_for(workspace_id: uuid.UUID) -> Iterator[None]:
    """Every transaction started in this block, by any session, is limited to the workspace."""
    token = _workspace.set(workspace_id)
    try:
        yield
    finally:
        _workspace.reset(token)


def start_request() -> Token[uuid.UUID | None]:
    """A request starts acting for no workspace; `end_request` restores the previous state."""
    return _workspace.set(None)


def end_request(token: Token[uuid.UUID | None]) -> None:
    _workspace.reset(token)


async def bind_workspace(session: AsyncSession, workspace_id: uuid.UUID) -> None:
    """Act for the workspace for the rest of this request, starting with the current
    transaction of `session`."""
    _workspace.set(workspace_id)
    session.info.pop(EXPLICIT, None)
    await apply_now(session)


def mode_of(session: Session | AsyncSession) -> Mode:
    info = session.info
    if info.get(EXPLICIT) == SYSTEM:
        return SYSTEM
    workspace_id = _workspace.get()
    if workspace_id is not None:
        return workspace_id
    if info.get(DEFAULT) == SYSTEM:
        return SYSTEM
    return None


def _apply(connection: Connection, mode: Mode) -> None:
    if mode == SYSTEM:
        if connection.info.pop(_SWITCHED, False):
            connection.exec_driver_sql(_RESET_SQL)
        return
    connection.exec_driver_sql(_TENANT_SQL, {"role": APP_ROLE, "ws": str(mode) if mode else ""})
    connection.info[_SWITCHED] = True


async def apply_now(session: AsyncSession) -> None:
    """Apply the session's mode to a transaction already in progress (a new one applies it
    by itself)."""
    if session.in_transaction():
        connection = await session.connection()
        await connection.run_sync(lambda sync: _apply(sync, mode_of(session)))


@event.listens_for(Session, "after_begin")
def _after_begin(
    session: Session, _transaction: SessionTransaction, connection: Connection
) -> None:
    _apply(connection, mode_of(session))


@event.listens_for(Engine, "commit")
@event.listens_for(Engine, "rollback")
def _transaction_ended(connection: Connection, *_args: Any) -> None:
    # SET LOCAL ended with the transaction.
    connection.info.pop(_SWITCHED, None)
