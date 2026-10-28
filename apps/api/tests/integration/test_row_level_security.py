"""F14 AC1-AC3, AC5: row-level security as a second isolation layer (ADR-0009).

Seeding runs as a system session; the checks then switch the same transaction to a tenant
(or to no workspace at all) and query **without** any workspace filter, as a buggy query would.
"""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from app.core import rls
from app.core.db import DB_SCHEMA
from app.documents.models import DocumentEvent
from app.llm.models import LlmCall
from app.mcp.models import ApiToken
from app.storage.fake import FakeStorage
from tests.support.documents import upload_document
from tests.support.identity import TwoWorkspaces

TENANT_TABLES = text(
    """
    SELECT c.table_name FROM information_schema.columns c
    JOIN information_schema.tables t USING (table_schema, table_name)
    WHERE c.table_schema = :schema AND c.column_name = 'workspace_id'
      AND t.table_type = 'BASE TABLE'
    ORDER BY 1
    """
)


async def tenant_tables(connection: AsyncConnection | AsyncSession) -> list[str]:
    return list((await connection.execute(TENANT_TABLES, {"schema": DB_SCHEMA})).scalars())


async def test_ac1_every_tenant_table_has_rls_and_the_tenant_policy(
    db_engine: AsyncEngine,
) -> None:
    async with db_engine.connect() as connection:
        tables = await tenant_tables(connection)
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT c.relname, c.relrowsecurity,
                      EXISTS (SELECT 1 FROM pg_policy p WHERE p.polrelid = c.oid
                              AND p.polname = 'tenant'
                              AND p.polroles = ARRAY['docflow_app'::regrole::oid]) AS policy,
                      has_table_privilege('docflow_app', c.oid, 'SELECT,INSERT,UPDATE,DELETE')
                        AS granted
                    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = :schema AND c.relname = ANY(:tables)
                    """
                ),
                {"schema": DB_SCHEMA, "tables": [*tables, "workspaces"]},
            )
        ).all()

    problems = [
        f"{row.relname}: rls={row.relrowsecurity} policy={row.policy} granted={row.granted}"
        for row in rows
        if not (row.relrowsecurity and row.policy and row.granted)
    ]
    assert not problems, "\n".join(problems)
    assert len(rows) == len(tables) + 1
    assert {"documents", "memberships", "api_tokens", "llm_calls"} <= set(tables)


@pytest.fixture
async def seeded(
    db_client: httpx.AsyncClient,
    db_session: AsyncSession,
    two_workspaces: TwoWorkspaces,
    fake_storage: FakeStorage,
) -> TwoWorkspaces:
    """A document (upload, event, job), an LLM call and an access token in each workspace."""
    w = two_workspaces
    now = datetime.now(UTC)
    for workspace, user in ((w.a, w.a_admin), (w.b, w.b_admin)):
        document = await upload_document(db_client, fake_storage, workspace.id, user)
        db_session.add_all(
            [
                LlmCall(
                    workspace_id=workspace.id,
                    document_id=uuid.UUID(document["id"]),
                    task="classify",
                    provider="gemini",
                    model="m",
                    prompt_version="classify/v1",
                    attempt=1,
                    outcome="ok",
                    latency_ms=1,
                ),
                ApiToken(
                    workspace_id=workspace.id,
                    user_id=user.id,
                    name="t",
                    prefix="dfw_xxxx",
                    token_hash=uuid.uuid4().hex,
                    expires_at=now + timedelta(days=1),
                ),
            ]
        )
    await db_session.commit()
    return w


async def visible_workspaces(session: AsyncSession, table: str) -> set[uuid.UUID]:
    column = "id" if table == "workspaces" else "workspace_id"
    rows = await session.execute(text(f"SELECT DISTINCT {column} FROM docflow.{table}"))  # noqa: S608  # table names from the catalogue
    return set(rows.scalars())


async def test_ac2_queries_without_a_filter_see_only_the_current_workspace(
    db_session: AsyncSession, seeded: TwoWorkspaces
) -> None:
    w = seeded
    tables = [*await tenant_tables(db_session), "workspaces"]
    as_system = {table: await visible_workspaces(db_session, table) for table in tables}

    await rls.bind_workspace(db_session, w.a.id)
    as_tenant = {table: await visible_workspaces(db_session, table) for table in tables}

    for table in ("documents", "uploads", "document_events", "jobs", "llm_calls", "api_tokens"):
        assert as_system[table] == {w.a.id, w.b.id}, table  # both were seeded
    assert {table: seen for table, seen in as_tenant.items() if seen - {w.a.id}} == {}
    assert as_tenant["documents"] == {w.a.id}


async def test_ac2_writing_another_workspaces_row_is_refused(
    db_session: AsyncSession, seeded: TwoWorkspaces
) -> None:
    w = seeded
    their_document = await db_session.scalar(
        text("SELECT id FROM docflow.documents WHERE workspace_id = :b"), {"b": w.b.id}
    )
    await rls.bind_workspace(db_session, w.a.id)

    db_session.add(
        DocumentEvent(workspace_id=w.b.id, document_id=their_document, to_status="FAILED")
    )
    with pytest.raises(ProgrammingError, match="row-level security"):
        await db_session.flush()
    await db_session.rollback()


async def test_ac3_a_session_with_no_workspace_sees_nothing(
    db_connection: AsyncConnection, db_session: AsyncSession, seeded: TwoWorkspaces
) -> None:
    unbound = AsyncSession(bind=db_connection, join_transaction_mode="create_savepoint")

    documents = await unbound.scalar(text("SELECT count(*) FROM docflow.documents"))
    workspaces = await unbound.scalar(text("SELECT count(*) FROM docflow.workspaces"))
    users = await unbound.scalar(text("SELECT count(*) FROM docflow.users"))
    await unbound.close()

    assert (documents, workspaces) == (0, 0)
    assert (users or 0) >= 3  # users are global, not tenant data


async def test_ac5_data_api_style_roles_read_nothing(
    db_session: AsyncSession, seeded: TwoWorkspaces
) -> None:
    role = f"docflow_test_anon_{uuid.uuid4().hex[:8]}"  # created and dropped with the rollback
    await db_session.execute(text(f"CREATE ROLE {role} NOLOGIN"))
    await db_session.execute(text(f"GRANT USAGE ON SCHEMA docflow TO {role}"))
    await db_session.execute(text(f"GRANT SELECT ON ALL TABLES IN SCHEMA docflow TO {role}"))
    await db_session.execute(text(f"SET LOCAL ROLE {role}"))

    documents = await db_session.scalar(text("SELECT count(*) FROM docflow.documents"))
    tokens = await db_session.scalar(text("SELECT count(*) FROM docflow.api_tokens"))

    assert (documents, tokens) == (0, 0)
