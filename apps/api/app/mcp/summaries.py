"""Vendor and spend aggregates for the MCP tools (F12 AC5, D3, D4).

They read the typed columns copied from each document's current extraction (ADR-0005 §4).
An approved document can't change after approval, so for approved documents those columns
are the approved values. Totals are per currency and never added across currencies.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import ColumnElement, SQLColumnExpression, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import WorkspaceScope
from app.documents.models import Document, DocumentStatus

GroupBy = Literal["vendor", "month", "doc_type"]
MAX_GROUPS = 100
MAX_VENDORS = 50


@dataclass
class Vendor:
    name: str
    documents: int = 0
    approved_documents: int = 0
    last_document_date: date | None = None
    approved_totals: dict[str, Decimal] = field(default_factory=dict)


async def list_vendors(
    session: AsyncSession, scope: WorkspaceScope, *, name_contains: str | None
) -> list[Vendor]:
    """Vendors by number of documents, with approved totals per currency."""
    approved = Document.status == DocumentStatus.APPROVED
    conditions = [Document.workspace_id == scope.workspace_id, Document.vendor_name.is_not(None)]
    if name_contains:
        conditions.append(Document.vendor_name.icontains(name_contains, autoescape=True))
    rows = await session.execute(
        select(
            Document.vendor_name,
            Document.currency,
            func.count(),
            func.count().filter(approved),
            func.max(Document.document_date),
            func.sum(Document.total_amount).filter(approved),
        )
        .where(*conditions)
        .group_by(Document.vendor_name, Document.currency)
    )
    vendors: dict[str, Vendor] = {}
    for name, currency, documents, approved_documents, last_date, total in rows:
        vendor = vendors.setdefault(str(name), Vendor(name=str(name)))
        vendor.documents += documents
        vendor.approved_documents += approved_documents
        if last_date and (
            vendor.last_document_date is None or last_date > vendor.last_document_date
        ):
            vendor.last_document_date = last_date
        if currency and total is not None:
            vendor.approved_totals[currency] = total
    ranked = sorted(vendors.values(), key=lambda v: (-v.documents, v.name.lower()))
    return ranked[:MAX_VENDORS]


@dataclass(frozen=True)
class SpendGroup:
    key: str
    currency: str
    documents: int
    total: Decimal


@dataclass(frozen=True)
class Spend:
    groups: list[SpendGroup]
    without_total: int  # matching documents with no total or currency, left out of the sums


async def spend_summary(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    group_by: GroupBy,
    date_from: date | None,
    date_to: date | None,
    vendor: str | None,
    include_unapproved: bool,
) -> Spend:
    statuses = [DocumentStatus.APPROVED]
    if include_unapproved:
        statuses.append(DocumentStatus.NEEDS_REVIEW)
    conditions: list[ColumnElement[bool]] = [
        Document.workspace_id == scope.workspace_id,
        Document.status.in_(statuses),
    ]
    if date_from:
        conditions.append(Document.document_date >= date_from)
    if date_to:
        conditions.append(Document.document_date <= date_to)
    if vendor:
        conditions.append(Document.vendor_name.icontains(vendor, autoescape=True))
    key: SQLColumnExpression[Any] = {
        "vendor": Document.vendor_name,
        "month": func.to_char(Document.document_date, "YYYY-MM"),
        "doc_type": Document.doc_type,
    }[group_by]
    total = func.sum(Document.total_amount)
    group = func.coalesce(key, literal_column("'unknown'"))  # one literal: GROUP BY must match
    rows = await session.execute(
        select(group, Document.currency, func.count(), total)
        .where(*conditions, Document.total_amount.is_not(None), Document.currency.is_not(None))
        .group_by(group, Document.currency)
        .order_by(Document.currency, total.desc())
        .limit(MAX_GROUPS)
    )
    without_total = await session.scalar(
        select(func.count()).where(
            *conditions, (Document.total_amount.is_(None)) | (Document.currency.is_(None))
        )
    )
    return Spend(
        groups=[
            SpendGroup(key=row[0], currency=row[1], documents=row[2], total=row[3]) for row in rows
        ],
        without_total=without_total or 0,
    )
