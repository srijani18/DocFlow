"""Approved data as spreadsheet rows (F9 plan §2). Pure functions: no database."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

DOCUMENT_COLUMNS = [
    "document_id",
    "file_name",
    "doc_type",
    "number",
    "document_date",
    "due_date",
    "vendor_name",
    "vendor_gstin",
    "buyer_name",
    "buyer_gstin",
    "currency",
    "subtotal",
    "cgst",
    "sgst",
    "igst",
    "other_tax",
    "tax_total",
    "total",
    "status",
    "approved_at",
    "approved_by",
    "corrections",
]
LINE_COLUMNS = [
    "document_id",
    "document_number",
    "line",
    "description",
    "hsn_sac",
    "quantity",
    "unit_price",
    "amount",
]
NUMBERS = {"invoice": "invoice_number", "receipt": "receipt_number", "purchase_order": "po_number"}
DATES = {"invoice": "invoice_date", "receipt": "date", "purchase_order": "po_date"}
LATER = {"invoice": "due_date", "purchase_order": "delivery_date"}
TAX_COLUMNS = {"CGST": "cgst", "SGST": "sgst", "IGST": "igst"}

Cell = str | Decimal | int | None


@dataclass(frozen=True)
class ExportedDocument:
    """One document as exported: its metadata and the data of the exported version."""

    id: str
    filename: str
    doc_type: str | None
    status: str
    approved_at: datetime | None
    approved_by: str | None  # an email, "agent", or None
    corrections: int
    data: Mapping[str, Any]


CENTS = Decimal("0.01")


def _amount(money: Any) -> Decimal | None:
    """A money amount with at least two decimals (16826.8 → 16826.80), never fewer digits
    than were stored (AC4)."""
    if not isinstance(money, Mapping) or money.get("amount") is None:
        return None
    amount = Decimal(str(money["amount"]))
    exponent = amount.as_tuple().exponent
    return amount.quantize(CENTS) if isinstance(exponent, int) and exponent > -2 else amount


def _party(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    party = data.get(key)
    return party if isinstance(party, Mapping) else {}


def document_row(document: ExportedDocument) -> list[Cell]:
    data, doc_type = document.data, document.doc_type or ""
    seller = _party(data, "merchant" if doc_type == "receipt" else "vendor")
    buyer = _party(data, "buyer")
    taxes: dict[str, Decimal] = {}
    for line in data.get("taxes") or []:
        amount = _amount(line.get("amount")) if isinstance(line, Mapping) else None
        if amount is not None:
            column = TAX_COLUMNS.get(str(line.get("type")), "other_tax")
            taxes[column] = taxes.get(column, Decimal(0)) + amount
    tax_total = _amount(data.get("tax_total")) if doc_type == "receipt" else None
    if tax_total is None and taxes:
        tax_total = sum(taxes.values(), Decimal(0))
    total = data.get("total")
    return [
        document.id,
        document.filename,
        doc_type or None,
        data.get(NUMBERS.get(doc_type, "")),
        data.get(DATES.get(doc_type, "")),
        data.get(LATER.get(doc_type, "")),
        seller.get("name"),
        seller.get("gstin"),
        buyer.get("name"),
        buyer.get("gstin"),
        data.get("currency") or (total.get("currency") if isinstance(total, Mapping) else None),
        _amount(data.get("subtotal")),
        taxes.get("cgst"),
        taxes.get("sgst"),
        taxes.get("igst"),
        taxes.get("other_tax"),
        tax_total,
        _amount(total),
        document.status,
        document.approved_at.isoformat(timespec="seconds") if document.approved_at else None,
        document.approved_by,
        document.corrections,
    ]


def line_rows(document: ExportedDocument) -> list[list[Cell]]:
    number = document.data.get(NUMBERS.get(document.doc_type or "", ""))
    rows: list[list[Cell]] = []
    for index, item in enumerate(document.data.get("line_items") or [], start=1):
        if not isinstance(item, Mapping):
            continue
        quantity = item.get("quantity")
        rows.append(
            [
                document.id,
                number,
                index,
                item.get("description"),
                item.get("hsn_sac"),
                None if quantity is None else Decimal(str(quantity)),
                _amount(item.get("unit_price")),
                _amount(item.get("amount")),
            ]
        )
    return rows
