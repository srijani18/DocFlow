"""Validation rules (F6). Other modules use this facade (ADR-0002)."""

import uuid
from collections.abc import AsyncIterator, Callable, Collection, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.tenancy import WorkspaceScope
from app.extractions import service as extractions
from app.validation import repository
from app.validation.checks import NUMBER_FIELDS, Issue, WorkspaceLookups
from app.validation.models import ValidationIssue

SEVERITIES = ("error", "warning", "info")


def lookups_for(
    sessionmaker: async_sessionmaker[AsyncSession],
    scope: WorkspaceScope,
    *,
    document_id: uuid.UUID,
    doc_type: str,
) -> WorkspaceLookups:
    """The duplicate and known-vendor lookups, limited to the document's workspace. Each opens
    its own short session, so no connection is held while the model rereads."""
    return _lookups(sessionmaker, scope, document_id=document_id, doc_type=doc_type)


def lookups_in(
    session: AsyncSession, scope: WorkspaceScope, *, document_id: uuid.UUID, doc_type: str
) -> WorkspaceLookups:
    """The same lookups inside an open transaction (a reviewer's save, F7 AC4)."""

    @asynccontextmanager
    async def current() -> AsyncIterator[AsyncSession]:
        yield session

    return _lookups(current, scope, document_id=document_id, doc_type=doc_type)


def _lookups(
    open_session: Callable[[], AbstractAsyncContextManager[AsyncSession]],
    scope: WorkspaceScope,
    *,
    document_id: uuid.UUID,
    doc_type: str,
) -> WorkspaceLookups:
    async def find_duplicates(gstin: str | None, name: str | None, number: str) -> list[str]:
        async with open_session() as session:
            ids = await repository.find_duplicates(
                session,
                scope,
                document_id=document_id,
                doc_type=doc_type,
                number_field=NUMBER_FIELDS[doc_type],
                number=number,
                gstin=gstin,
                name=name,
            )
        return [str(id_) for id_ in ids]

    async def vendor_seen(gstin: str | None, name: str | None) -> bool:
        async with open_session() as session:
            return await repository.vendor_seen(
                session, scope, document_id=document_id, gstin=gstin, name=name
            )

    return WorkspaceLookups(find_duplicates=find_duplicates, vendor_seen=vendor_seen)


async def record_issues(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    document_id: uuid.UUID,
    extraction_id: uuid.UUID,
    remaining: Sequence[Issue],
    fixed: Sequence[Issue],
) -> None:
    """Store the issues found on a version: the ones still open, and the ones the agent fixed
    on the way to it (AC2)."""
    await repository.insert_issues(
        session,
        scope,
        [
            {
                "document_id": document_id,
                "extraction_id": extraction_id,
                "check_name": issue.check,
                "severity": issue.severity,
                "paths": list(issue.paths),
                "message": issue.message,
                "fixed_by_agent": was_fixed,
            }
            for issues, was_fixed in ((remaining, False), (fixed, True))
            for issue in issues
        ],
    )


async def list_current_issues(
    session: AsyncSession, scope: WorkspaceScope, document_id: str
) -> list[ValidationIssue]:
    """Issues for the document's current extraction; 404 until one exists."""
    extraction = await extractions.get_current(session, scope, document_id)
    return await repository.list_for_extraction(session, scope, extraction.id)


async def open_issue_counts(
    session: AsyncSession, scope: WorkspaceScope, extraction_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, dict[str, int]]:
    """Unfixed issues per extraction, with every severity present (0 when none)."""
    counts = await repository.open_counts(session, scope, extraction_ids)
    return {
        extraction_id: {
            severity: counts.get(extraction_id, {}).get(severity, 0) for severity in SEVERITIES
        }
        for extraction_id in extraction_ids
    }


async def open_errors(
    session: AsyncSession, scope: WorkspaceScope, extraction_id: uuid.UUID
) -> list[ValidationIssue]:
    """Unfixed `error` issues on a version: approving over them needs a confirmation (F7)."""
    return [
        issue
        for issue in await repository.list_for_extraction(session, scope, extraction_id)
        if issue.severity == "error" and not issue.fixed_by_agent
    ]
