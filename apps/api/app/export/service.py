"""Export (F9): the selected documents as a CSV pair in a ZIP, or as JSON, streamed."""

import io
import json
import uuid
import zipfile
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.tenancy import WorkspaceScope
from app.export import repository
from app.export.csv_writer import to_csv
from app.export.rows import (
    DOCUMENT_COLUMNS,
    LINE_COLUMNS,
    ExportedDocument,
    document_row,
    line_rows,
)
from app.extractions.exact_json import dumps_exact
from app.search import service as search
from app.search.repository import Filters

MAX_DOCUMENTS = 5_000  # AC6
PAGE = 500
AGENT = "agent"

Format = Literal["csv", "json"]


class TooManyDocumentsError(AppError):
    status = 422
    type_slug = "export-too-large"
    title = "Too many documents to export"


class Selection:
    """Which documents an export contains: the filters, plus the search text if any. With
    text, exactly what the search shows (keyword and meaning, best first); without, every
    match newest first."""

    def __init__(
        self,
        scope: WorkspaceScope,
        filters: Filters,
        *,
        include_unapproved: bool,
        ids: list[uuid.UUID] | None,
    ) -> None:
        self.scope = scope
        self.filters = filters
        self.include_unapproved = include_unapproved
        self.ids = ids


async def select(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    text: str,
    filters: Filters,
    include_unapproved: bool,
    embed_query: search.QueryEmbedder,
) -> Selection:
    ids = None
    if text.strip():
        found = await search.search(
            session,
            scope,
            text=text,
            filters=filters,
            offset=0,
            limit=search.MAX_RESULTS,
            embed_query=embed_query,
        )
        ids = [hit.document.id for hit in found.hits]
    selection = Selection(scope, filters, include_unapproved=include_unapproved, ids=ids)
    total = await repository.count(
        session, scope, filters, include_unapproved=include_unapproved, ids=ids
    )
    if total > MAX_DOCUMENTS:
        raise TooManyDocumentsError(
            f"{total:,} documents match. Narrow the filters to {MAX_DOCUMENTS:,} or fewer."
        )
    return selection


def _exported(row: repository.Row) -> ExportedDocument:
    document, data, approver_email, corrections = row
    approved_by = None
    if document.approved_at is not None:
        approved_by = AGENT if document.approved_by_agent else approver_email
    return ExportedDocument(
        id=str(document.id),
        filename=document.filename,
        doc_type=document.doc_type,
        status=document.status,
        approved_at=document.approved_at,
        approved_by=approved_by,
        corrections=corrections,
        data=json.loads(data, parse_float=Decimal),
    )


async def documents(session: AsyncSession, selection: Selection) -> AsyncIterator[ExportedDocument]:
    """The selected documents, a page at a time, so memory stays flat (AC6)."""
    if selection.ids is not None:
        for start in range(0, len(selection.ids), PAGE):
            for row in await repository.by_ids(
                session,
                selection.scope,
                selection.filters,
                include_unapproved=selection.include_unapproved,
                ids=selection.ids[start : start + PAGE],
            ):
                yield _exported(row)
        return
    after = None
    while True:
        rows = await repository.page(
            session,
            selection.scope,
            selection.filters,
            include_unapproved=selection.include_unapproved,
            after=after,
            limit=PAGE,
        )
        for row in rows:
            yield _exported(row)
        if len(rows) < PAGE:
            return
        after = (rows[-1][0].created_at, rows[-1][0].id)


class _Chunks(io.RawIOBase):
    """A write-only stream that hands what zipfile writes to the response."""

    def __init__(self) -> None:
        self.pending: list[bytes] = []

    def writable(self) -> bool:
        return True

    def write(self, data: Any) -> int:
        self.pending.append(bytes(data))
        return len(data)

    def take(self) -> bytes:
        chunk, self.pending = b"".join(self.pending), []
        return chunk


async def csv_zip(session: AsyncSession, selection: Selection) -> AsyncIterator[bytes]:
    """documents.csv, then line_items.csv, in one ZIP written as it streams (AC2)."""
    sink = _Chunks()
    with zipfile.ZipFile(sink, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, header, rows_of in (
            ("documents.csv", DOCUMENT_COLUMNS, lambda d: [document_row(d)]),
            ("line_items.csv", LINE_COLUMNS, line_rows),
        ):
            with archive.open(name, mode="w", force_zip64=True) as entry:
                entry.write(to_csv([], header=header).encode())
                async for document in documents(session, selection):
                    entry.write(to_csv(rows_of(document)).encode())
                    if sink.pending:
                        yield sink.take()
            yield sink.take()
    yield sink.take()


async def json_array(session: AsyncSession, selection: Selection) -> AsyncIterator[bytes]:
    """[{document: {...}, data: {...}}, ...] with exact amounts (AC3)."""
    yield b"["
    first = True
    async for document in documents(session, selection):
        item = {
            "document": {
                "id": document.id,
                "file_name": document.filename,
                "doc_type": document.doc_type,
                "status": document.status,
                "approved_at": document.approved_at.isoformat() if document.approved_at else None,
                "approved_by": document.approved_by,
                "corrections": document.corrections,
            },
            "data": document.data,
        }
        yield (b"" if first else b",") + dumps_exact(item).encode()
        first = False
    yield b"]"
