"""F13 AC7: time the metrics queries for a workspace with 10,000 documents and 100,000 LLM calls.

Seeds a throwaway workspace in the local test database with generated rows (spread over 60
days, with events, extractions, corrections and jobs), analyses the tables as autovacuum
would, times each period a few times, then deletes the workspace.

    make metrics-perf
"""

import asyncio
import statistics
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import DatabaseSettings
from app.core.db import create_engine
from app.core.rls import acting_for
from app.core.rls_system import system_sessionmaker
from app.core.tenancy import WorkspaceScope
from app.identity.models import Membership, User, Workspace
from app.metrics import service
from app.metrics.schemas import Period
from app.models import import_all_models

TEST_DATABASE_URL = "postgresql://postgres:postgres@localhost:54320/docflow_test"
DOCUMENTS = 10_000
CALLS = 100_000
RUNS = 5
BUDGET_SECONDS = 1.0

# {ws} and {user} are ids this script generated; every row is spread over the last 60 days.
SEED = [
    """
    INSERT INTO docflow.uploads (id, workspace_id, created_by_user_id, filename, content_type,
                                 size_bytes, sha256, expires_at, created_at)
    SELECT md5('{ws}' || n)::uuid, '{ws}'::uuid, '{user}'::uuid, 'scan-' || n || '.pdf',
           'application/pdf', 1000,
           md5('sha' || '{ws}' || n), now(), now() - (n % 60) * interval '1 day'
    FROM generate_series(1, {documents}) n
    """,
    """
    INSERT INTO docflow.documents (id, workspace_id, upload_id, storage_path, filename,
        content_type, size_bytes, sha256, status, failure_reason, doc_type, created_by_user_id,
        created_at, status_changed_at, approved_at, approved_by_agent, approved_by_user_id)
    SELECT md5('{ws}' || n)::uuid, '{ws}'::uuid, md5('{ws}' || n)::uuid, 'perf/' || n,
           'scan-' || n || '.pdf', 'application/pdf', 1000, md5('sha' || '{ws}' || n),
           (ARRAY['APPROVED', 'APPROVED', 'APPROVED', 'NEEDS_REVIEW', 'FAILED'])[n % 5 + 1],
           CASE WHEN n % 5 = 4 THEN (ARRAY['No AI key', 'Unreadable file'])[n % 2 + 1] END,
           (ARRAY['invoice', 'receipt', 'purchase_order'])[n % 3 + 1], '{user}'::uuid,
           now() - (n % 60) * interval '1 day', now() - (n % 60) * interval '1 day',
           CASE WHEN n % 5 < 3 THEN now() - (n % 60) * interval '1 day' END,
           n % 5 = 0, CASE WHEN n % 5 IN (1, 2) THEN '{user}'::uuid END
    FROM generate_series(1, {documents}) n
    """,
    """
    INSERT INTO docflow.extractions (id, workspace_id, document_id, version, source, schema_id,
                                     data, processing_generation)
    SELECT md5('x' || '{ws}' || n)::uuid, '{ws}'::uuid, md5('{ws}' || n)::uuid, 1, 'model',
           'docflow/invoice/v1',
           jsonb_build_object(
               'invoice_number', 'INV-' || n, 'invoice_date', '2026-01-01',
               'vendor', jsonb_build_object('name', 'Vendor ' || n % 50, 'gstin', null),
               'totals', jsonb_build_object('subtotal', 100, 'tax', 18, 'total', 118),
               'line_items', (SELECT jsonb_agg(jsonb_build_object(
                   'description', 'Item ' || i, 'quantity', i, 'rate', 10, 'amount', 10 * i))
                   FROM generate_series(1, 4) i)),
           1
    FROM generate_series(1, {documents}) n
    """,
    """
    UPDATE docflow.documents
    SET approved_extraction_id = md5('x' || '{ws}' || substr(storage_path, 6))::uuid
    WHERE workspace_id = '{ws}'::uuid AND status = 'APPROVED'
    """,
    """
    INSERT INTO docflow.corrections (workspace_id, document_id, extraction_id, path, old_value,
                                     new_value, user_id)
    SELECT '{ws}'::uuid, md5('{ws}' || n)::uuid, md5('x' || '{ws}' || n)::uuid, 'totals.total',
           '1', '2', '{user}'::uuid
    FROM generate_series(1, {documents}) n WHERE n % 5 = 1
    """,
    """
    INSERT INTO docflow.document_events (workspace_id, document_id, from_status, to_status,
                                         created_at)
    SELECT '{ws}'::uuid, md5('{ws}' || n)::uuid, NULL, s.status,
           now() - (n % 60) * interval '1 day' + s.step * (n % 7 + 1) * interval '3 seconds'
    FROM generate_series(1, {documents}) n,
         (VALUES (0, 'UPLOADED'), (1, 'CLASSIFYING'), (2, 'EXTRACTING'), (3, 'VALIDATING'),
                 (4, 'NEEDS_REVIEW')) AS s(step, status)
    """,
    """
    INSERT INTO docflow.llm_calls (workspace_id, document_id, task, provider, model,
        prompt_version, attempt, outcome, cost_usd, latency_ms, fallback, created_at)
    SELECT '{ws}'::uuid,
           CASE WHEN n % 20 = 0 THEN NULL ELSE md5('{ws}' || (n % {documents} + 1))::uuid END,
           (ARRAY['classify', 'extract', 'validate', 'embed'])[n % 4 + 1],
           CASE WHEN n % 10 = 0 THEN 'groq' ELSE 'gemini' END, 'model-' || n % 3, 'v1', 1,
           (ARRAY['ok', 'ok', 'ok', 'ok', 'ok', 'ok', 'cache_hit', 'error', 'invalid_output',
                  'skipped'])[n % 10 + 1],
           0.0001 * (n % 17), 500 + n % 4000, n % 10 = 0,
           now() - (n % 60) * interval '1 day'
    FROM generate_series(1, {calls}) n
    """,
    """
    INSERT INTO docflow.jobs (workspace_id, document_id, kind, status, idempotency_key,
                              created_at)
    SELECT '{ws}'::uuid, md5('{ws}' || n)::uuid, 'process_document',
           CASE WHEN n % 1000 = 0 THEN 'dead' WHEN n % 997 = 0 THEN 'queued'
                ELSE 'succeeded' END,
           'perf:' || '{ws}' || ':' || n, now() - (n % 60) * interval '1 day'
    FROM generate_series(1, {documents}) n
    """,
]
TABLES = ["documents", "document_events", "extractions", "corrections", "llm_calls", "jobs"]


async def _create(session: AsyncSession) -> WorkspaceScope:
    user = User(auth_subject=f"metrics-perf-{uuid.uuid4()}", email=None)
    session.add(user)
    await session.flush()
    workspace = Workspace(name="Metrics perf (temporary)", created_by_user_id=user.id)
    session.add(workspace)
    await session.flush()
    session.add(Membership(workspace_id=workspace.id, user_id=user.id, role="admin"))
    scope = WorkspaceScope(workspace_id=workspace.id, user_id=user.id, role="admin")
    for statement in SEED:
        sql = statement.format(ws=workspace.id, user=user.id, documents=DOCUMENTS, calls=CALLS)
        await session.execute(text(sql))
    await session.commit()
    return scope


async def _delete(session: AsyncSession, scope: WorkspaceScope) -> None:
    await session.execute(
        text("DELETE FROM docflow.workspaces WHERE id = :ws"), {"ws": scope.workspace_id}
    )
    await session.execute(text("DELETE FROM docflow.users WHERE id = :u"), {"u": scope.user_id})
    await session.commit()


async def main() -> int:
    import_all_models()
    engine = create_engine(DatabaseSettings(database_url=TEST_DATABASE_URL))
    sessionmaker = system_sessionmaker(engine)
    async with sessionmaker() as session:
        started = time.perf_counter()
        scope = await _create(session)
        print(
            f"Seeded {DOCUMENTS:,} documents and {CALLS:,} calls in "
            f"{time.perf_counter() - started:.1f} s"
        )
        try:
            async with engine.connect() as connection:
                autocommit = await connection.execution_options(isolation_level="AUTOCOMMIT")
                for table in TABLES:
                    await autocommit.execute(text(f"ANALYZE docflow.{table}"))
            slowest = 0.0
            periods: tuple[Period, ...] = ("7d", "30d", "all")
            for period in periods:
                timings = []
                for _ in range(RUNS):
                    started = time.perf_counter()
                    # As the API runs it: under row-level security for the workspace (F14 AC4).
                    with acting_for(scope.workspace_id):
                        result = await service.workspace_metrics(
                            session, scope, period, datetime.now(UTC)
                        )
                    timings.append(time.perf_counter() - started)
                    await session.rollback()
                slowest = max(slowest, *timings)
                print(
                    f"{period:>4}: median {statistics.median(timings) * 1000:.0f} ms, "
                    f"max {max(timings) * 1000:.0f} ms "
                    f"({result.headline.processing_runs:,} runs, "
                    f"{sum(task.calls for task in result.llm):,} calls)"
                )
        finally:
            await _delete(session, scope)
    await engine.dispose()
    print(f"AC7 (< {BUDGET_SECONDS:.0f} s): {'pass' if slowest < BUDGET_SECONDS else 'FAIL'}")
    return 0 if slowest < BUDGET_SECONDS else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
