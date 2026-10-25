"""Fields copied from the current extraction onto the document (ADR-0005 §4, F5 AC7)."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

# Per document type: where the vendor, the document date and the total live in `data`.
_PATHS = {
    "invoice": ("vendor.name", "invoice_date"),
    "receipt": ("merchant.name", "date"),
    "purchase_order": ("vendor.name", "po_date"),
}


@dataclass(frozen=True)
class Summary:
    vendor_name: str | None = None
    document_date: date | None = None
    total_amount: Decimal | None = None
    currency: str | None = None


def _get(data: Mapping[str, Any], path: str) -> Any:
    node: Any = data
    for part in path.split("."):
        if not isinstance(node, Mapping):
            return None
        node = node.get(part)
    return node


def summarize(doc_type: str, data: Mapping[str, Any]) -> Summary:
    vendor_path, date_path = _PATHS[doc_type]
    raw_date = _get(data, date_path)
    raw_total = _get(data, "total.amount")
    try:
        total = None if raw_total is None else Decimal(str(raw_total)).quantize(Decimal("0.01"))
    except InvalidOperation:
        total = None
    return Summary(
        vendor_name=_get(data, vendor_path),
        document_date=date.fromisoformat(raw_date) if raw_date else None,
        total_amount=total,
        currency=_get(data, "total.currency") or data.get("currency"),
    )
