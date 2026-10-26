"""The sentence a document is embedded as (F8 D3). Readable text embeds better than raw JSON."""

from decimal import Decimal
from typing import Any

LABELS = {"invoice": "Invoice", "receipt": "Receipt", "purchase_order": "Purchase order"}
NUMBERS = {"invoice": "invoice_number", "receipt": "receipt_number", "purchase_order": "po_number"}
DATES = {"invoice": "invoice_date", "receipt": "date", "purchase_order": "po_date"}


def _party(party: Any) -> str | None:
    if not isinstance(party, dict) or not party.get("name"):
        return None
    address = party.get("address") if isinstance(party.get("address"), dict) else {}
    place = ", ".join(str(address[k]) for k in ("city", "state") if address and address.get(k))
    return f"{party['name']} ({place})" if place else str(party["name"])


def _money(value: Any) -> str | None:
    if not isinstance(value, dict) or value.get("amount") is None:
        return None
    return f"{value.get('currency') or ''} {Decimal(str(value['amount'])):,.2f}".strip()


def embedding_text(doc_type: str, data: dict[str, Any]) -> str:
    parts = [
        f"{LABELS.get(doc_type, doc_type)} {data.get(NUMBERS.get(doc_type, ''), '') or ''}".strip()
    ]
    seller = _party(data.get("merchant") if doc_type == "receipt" else data.get("vendor"))
    if seller:
        parts.append(f"from {seller}")
    buyer = _party(data.get("buyer"))
    if buyer:
        parts.append(f"to {buyer}")
    items = [
        str(item["description"])
        for item in data.get("line_items") or []
        if isinstance(item, dict) and item.get("description")
    ]
    if items:
        parts.append("items: " + ", ".join(items))
    if total := _money(data.get("total")):
        parts.append(f"total {total}")
    if date := data.get(DATES.get(doc_type, "")):
        parts.append(f"dated {date}")
    return "; ".join(parts)
