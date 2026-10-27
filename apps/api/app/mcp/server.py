"""The MCP server and its four read-only tools (F12 AC5-AC8, plan §4).

Every tool acts in the workspace of the access token the request was authenticated with
(`app.mcp.http`), reuses the feature services, and is logged without its arguments or
results.
"""

import time
import uuid
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.core.observability import report_exception
from app.core.rls import acting_for, bind_workspace
from app.core.tenancy import WorkspaceScope
from app.documents import service as documents
from app.documents.models import DocType, Document, DocumentStatus
from app.extractions import service as extractions
from app.mcp import summaries
from app.mcp.tokens import VerifiedToken
from app.search import service as search
from app.search.repository import Filters
from app.search.service import QueryEmbedder
from app.validation import service as validation

log = get_logger(__name__)

STATE_KEY = "docflow_access"  # where the HTTP layer puts the verified access token
READ_ONLY = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
MAX_SEARCH_RESULTS = 20
INSTRUCTIONS = """\
DocFlow holds a workspace's invoices, receipts and purchase orders, with the fields extracted \
from each (vendor, dates, line items, taxes, totals) and whether a person or DocFlow's \
validation agent approved them.
- Use search_documents to find documents by words or meaning, with optional filters.
- Use get_document for one document's extracted data and open validation issues.
- Use list_vendors and spend_summary for questions about vendors and spend.
Spend only counts approved documents unless asked otherwise, and amounts are per currency: \
never add amounts in different currencies together. Amounts are exact decimals, as strings."""

SessionOpener = Callable[[], AbstractAsyncContextManager[AsyncSession]]


@dataclass
class McpDeps:
    """What the tools need. Mutable so tests can swap in their own session."""

    open_session: SessionOpener
    query_embedder: Callable[[WorkspaceScope], QueryEmbedder]
    clock: Clock
    web_base_url: str


def plain(value: Any) -> Any:
    """JSON-ready values: exact decimals as strings, dates as ISO strings."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [plain(item) for item in value]
    return value


def verified_token(ctx: Context) -> VerifiedToken:
    request = ctx.request_context.request
    token = getattr(request, "scope", {}).get("state", {}).get(STATE_KEY)
    if not isinstance(token, VerifiedToken):  # the HTTP layer always sets it; defensive
        raise ToolError("Not authenticated")
    return token


def build_mcp(deps: McpDeps) -> MCPServer:
    server = MCPServer(name="DocFlow", title="DocFlow documents", instructions=INSTRUCTIONS)

    async def run(
        ctx: Context,
        tool: str,
        work: Callable[[AsyncSession, WorkspaceScope], Awaitable[tuple[dict[str, Any], int]]],
    ) -> dict[str, Any]:
        token = verified_token(ctx)
        started = time.perf_counter()
        outcome, count = "ok", 0
        try:
            with acting_for(token.scope.workspace_id):
                async with deps.open_session() as session:
                    await bind_workspace(session, token.scope.workspace_id)
                    result, count = await work(session, token.scope)
        except NotFoundError:
            outcome = "not_found"
            raise ToolError("Not found in this workspace.") from None
        except Exception as exc:  # a bug: report it like any other crash (F16)
            outcome = "error"
            log.exception("mcp_tool_failed", tool=tool)
            report_exception(exc, workspace_id=token.scope.workspace_id)
            raise ToolError("Something went wrong. Try again later.") from None
        finally:
            # Never the arguments or results: search text and document data stay out (AC7).
            log.info(
                "mcp_tool_called",
                tool=tool,
                outcome=outcome,
                workspace_id=str(token.scope.workspace_id),
                client_id=str(token.token_id),
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
                results=count,
            )
        return plain(result)  # type: ignore[no-any-return]

    def summary(document: Document) -> dict[str, Any]:
        return {
            "id": document.id,
            "filename": document.filename,
            "type": document.doc_type,
            "status": document.status,
            "vendor": document.vendor_name,
            "date": document.document_date,
            "total": document.total_amount,
            "currency": document.currency,
            "link": f"{deps.web_base_url}/app/documents/{document.id}",
        }

    @server.tool(annotations=READ_ONLY)
    async def search_documents(
        ctx: Context,
        *,
        query: Annotated[
            str, Field(description="Words or a description; empty lists newest first")
        ] = "",
        doc_type: DocType | None = None,
        status: DocumentStatus | None = None,
        vendor: Annotated[str | None, Field(description="Part of the vendor's name")] = None,
        date_from: Annotated[date | None, Field(description="Document date, inclusive")] = None,
        date_to: date | None = None,
        amount_min: Decimal | None = None,
        amount_max: Decimal | None = None,
        limit: Annotated[int, Field(ge=1, le=MAX_SEARCH_RESULTS)] = 10,
    ) -> dict[str, Any]:
        """Find documents in the workspace by keyword and meaning, best match first."""

        async def work(session: AsyncSession, scope: WorkspaceScope) -> tuple[dict[str, Any], int]:
            page = await search.search(
                session,
                scope,
                text=query.strip()[:200],
                filters=Filters(
                    doc_type=doc_type,
                    status=status,
                    vendor=vendor.strip() if vendor else None,
                    date_from=date_from,
                    date_to=date_to,
                    amount_min=amount_min,
                    amount_max=amount_max,
                ),
                offset=0,
                limit=limit,
                embed_query=deps.query_embedder(scope),
            )
            result: dict[str, Any] = {
                "documents": [summary(hit.document) | {"snippet": hit.snippet} for hit in page.hits]
            }
            if query.strip() and not page.semantic:
                result["note"] = (
                    "Meaning search is unavailable (no AI key connected, or the provider is "
                    "down), so these are keyword matches only."
                )
            return result, len(page.hits)

        return await run(ctx, "search_documents", work)

    @server.tool(annotations=READ_ONLY)
    async def get_document(
        ctx: Context, *, document_id: Annotated[str, Field(description="A document id")]
    ) -> dict[str, Any]:
        """One document: its status, extracted data (the approved version when there is one)
        and open validation issues."""

        async def work(session: AsyncSession, scope: WorkspaceScope) -> tuple[dict[str, Any], int]:
            document = await documents.get_document(session, scope, document_id)
            extraction_id = document.approved_extraction_id or document.current_extraction_id
            data = (
                await extractions.get_exact_data(session, scope, extraction_id)
                if extraction_id
                else None
            )
            issues = (
                await validation.list_current_issues(session, scope, document_id)
                if document.current_extraction_id
                else []
            )
            return (
                summary(document)
                | {
                    "version": "approved"
                    if document.approved_extraction_id
                    else "not yet approved",
                    "approved_by": "validation agent"
                    if document.approved_by_agent
                    else ("a reviewer" if document.approved_extraction_id else None),
                    "data": data,
                    "open_issues": [
                        {
                            "severity": issue.severity,
                            "check": issue.check_name,
                            "message": issue.message,
                            "fields": issue.paths,
                        }
                        for issue in issues
                        if not issue.fixed_by_agent
                    ],
                },
                1,
            )

        return await run(ctx, "get_document", work)

    @server.tool(annotations=READ_ONLY)
    async def list_vendors(
        ctx: Context,
        *,
        name_contains: Annotated[str | None, Field(description="Part of a vendor's name")] = None,
    ) -> dict[str, Any]:
        """Vendors with their number of documents, last document date and approved totals per
        currency, most documents first (at most 50)."""

        async def work(session: AsyncSession, scope: WorkspaceScope) -> tuple[dict[str, Any], int]:
            vendors = await summaries.list_vendors(
                session, scope, name_contains=name_contains.strip() if name_contains else None
            )
            return {
                "vendors": [
                    {
                        "name": vendor.name,
                        "documents": vendor.documents,
                        "approved_documents": vendor.approved_documents,
                        "last_document_date": vendor.last_document_date,
                        "approved_totals": vendor.approved_totals,
                    }
                    for vendor in vendors
                ]
            }, len(vendors)

        return await run(ctx, "list_vendors", work)

    @server.tool(annotations=READ_ONLY)
    async def spend_summary(
        ctx: Context,
        *,
        group_by: summaries.GroupBy = "vendor",
        date_from: Annotated[date | None, Field(description="Document date, inclusive")] = None,
        date_to: date | None = None,
        vendor: Annotated[str | None, Field(description="Part of the vendor's name")] = None,
        include_unapproved: Annotated[
            bool, Field(description="Also count documents still waiting for review")
        ] = False,
    ) -> dict[str, Any]:
        """Total spend grouped by vendor, month or document type, per currency. Approved
        documents only unless include_unapproved is set."""

        async def work(session: AsyncSession, scope: WorkspaceScope) -> tuple[dict[str, Any], int]:
            spend = await summaries.spend_summary(
                session,
                scope,
                group_by=group_by,
                date_from=date_from,
                date_to=date_to,
                vendor=vendor.strip() if vendor else None,
                include_unapproved=include_unapproved,
            )
            return {
                "group_by": group_by,
                "counted": "approved and in-review documents"
                if include_unapproved
                else "approved documents",
                "groups": [
                    {
                        group_by: group.key,
                        "currency": group.currency,
                        "documents": group.documents,
                        "total": group.total,
                    }
                    for group in spend.groups
                ],
                "documents_without_total": spend.without_total,
            }, len(spend.groups)

        return await run(ctx, "spend_summary", work)

    return server
