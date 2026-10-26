"""Deterministic checks on extracted data, the agent's "tools" (F6 AC1, AC2, spec D1).

Each check returns issues and never calls a model. A check that doesn't apply (no line
items, no GSTIN, not INR) returns nothing.
"""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from app.validation import gstin as gstin_rules

ABSOLUTE_TOLERANCE = Decimal("1.00")
RELATIVE_TOLERANCE = Decimal("0.005")
# Rereading may fix these (AC3).
FIXABLE = frozenset({"line_items", "totals", "gstin", "amount_format"})
# No currency on these documents has more than two minor-unit digits.
MAX_AMOUNT_DECIMALS = 2

DATE_FIELDS = {"invoice": "invoice_date", "receipt": "date", "purchase_order": "po_date"}
LATER_FIELDS = {"invoice": "due_date", "purchase_order": "delivery_date"}
NUMBER_FIELDS = {
    "invoice": "invoice_number",
    "receipt": "receipt_number",
    "purchase_order": "po_number",
}
PARTY_FIELDS = ("vendor", "buyer", "merchant")


@dataclass(frozen=True)
class Issue:
    check: str
    severity: str  # error | warning | info
    paths: tuple[str, ...]
    message: str

    @property
    def fixable(self) -> bool:
        return self.check in FIXABLE and self.severity == "error"


def amounts_match(a: Decimal, b: Decimal) -> bool:
    """Within ₹1.00 or 0.5% of the larger amount, whichever is greater (spec D2)."""
    tolerance = max(ABSOLUTE_TOLERANCE, RELATIVE_TOLERANCE * max(abs(a), abs(b)))
    return abs(a - b) <= tolerance


def _amount(value: Any) -> Decimal | None:
    if isinstance(value, Mapping):
        value = value.get("amount")
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def check_line_items(doc_type: str, data: Mapping[str, Any]) -> list[Issue]:
    issues = []
    items = data.get("line_items") or []
    amounts = []
    for index, item in enumerate(items):
        amount = _amount(item.get("amount"))
        amounts.append(amount)
        quantity, unit = _amount(item.get("quantity")), _amount(item.get("unit_price"))
        if (
            amount is not None
            and quantity is not None
            and unit is not None
            and not amounts_match(quantity * unit, amount)
        ):
            issues.append(
                Issue(
                    "line_items",
                    "error",
                    (
                        f"line_items.{index}.quantity",
                        f"line_items.{index}.unit_price.amount",
                        f"line_items.{index}.amount.amount",
                    ),
                    f"Line {index + 1}: {quantity} x {unit} = {quantity * unit}, "
                    f"but the amount is {amount}.",
                )
            )
    subtotal = _amount(data.get("subtotal"))
    if items and subtotal is not None and all(a is not None for a in amounts):
        total = sum((a for a in amounts if a is not None), Decimal(0))
        if not amounts_match(total, subtotal):
            issues.append(
                Issue(
                    "line_items",
                    "error",
                    (
                        "subtotal.amount",
                        *(f"line_items.{i}.amount.amount" for i in range(len(items))),
                    ),
                    f"Line items add up to {total}, but the subtotal is {subtotal}.",
                )
            )
    return issues


def check_totals(doc_type: str, data: Mapping[str, Any]) -> list[Issue]:
    total = _amount(data.get("total"))
    if total is None:
        return []
    subtotal = _amount(data.get("subtotal"))
    if subtotal is None:
        amounts = [_amount(item.get("amount")) for item in data.get("line_items") or []]
        if not amounts or any(a is None for a in amounts):
            return []
        subtotal = sum((a for a in amounts if a is not None), Decimal(0))
    if doc_type == "receipt":
        taxes = _amount(data.get("tax_total")) or Decimal(0)
        tax_paths: tuple[str, ...] = ("tax_total.amount",)
    else:
        tax_lines = data.get("taxes") or []
        taxes = sum((_amount(t.get("amount")) or Decimal(0) for t in tax_lines), Decimal(0))
        tax_paths = tuple(f"taxes.{i}.amount.amount" for i in range(len(tax_lines)))
    if taxes > 0 and total > 0 and taxes > total:
        # Impossible on any document, and what a misread scale looks like when the
        # amounts still add up otherwise (60.0 read for 60,000 with 5,455 tax).
        return [
            Issue(
                "totals",
                "error",
                ("total.amount", "subtotal.amount", *tax_paths),
                f"Taxes of {taxes} are more than the total of {total}.",
            )
        ]
    if amounts_match(subtotal + taxes, total):
        return []
    if doc_type == "receipt" and amounts_match(subtotal, total):
        return []  # prices include tax; the tax line is for information (common on receipts)
    return [
        Issue(
            "totals",
            "error",
            ("total.amount", "subtotal.amount", *tax_paths),
            f"Subtotal {subtotal} plus taxes {taxes} is {subtotal + taxes}, "
            f"but the total is {total}.",
        )
    ]


def _money_amounts(value: Any, path: str = "") -> list[tuple[str, Any]]:
    """(path, amount) of every Money object ({amount, currency}) in the data."""
    if isinstance(value, Mapping):
        if "amount" in value and "currency" in value:
            return [(f"{path}.amount" if path else "amount", value["amount"])]
        return [
            found
            for key, child in value.items()
            for found in _money_amounts(child, f"{path}.{key}" if path else str(key))
        ]
    if isinstance(value, list):
        return [
            found
            for index, child in enumerate(value)
            for found in _money_amounts(child, f"{path}.{index}")
        ]
    return []


def check_amount_format(doc_type: str, data: Mapping[str, Any]) -> list[Issue]:
    """An amount like 60.000 is almost always 60,000 with a dot as the thousands
    separator (common on Indonesian and European receipts). Every amount on the document
    is usually read the same way, so the arithmetic still adds up: only the format shows it.
    Found by the agent eval (F6 AC10)."""
    issues = []
    for path, value in _money_amounts(data):
        amount = _amount(value)
        if amount is None:
            continue
        exponent = amount.as_tuple().exponent
        if isinstance(exponent, int) and -exponent > MAX_AMOUNT_DECIMALS:
            issues.append(
                Issue(
                    "amount_format",
                    "error",
                    (path,),
                    f"{path} is {amount}: more than two decimal places usually means a "
                    "thousands separator was read as a decimal point.",
                )
            )
    return issues


def check_gstins(doc_type: str, data: Mapping[str, Any]) -> list[Issue]:
    issues = []
    for party in PARTY_FIELDS:
        value = (data.get(party) or {}).get("gstin")
        if not value:
            continue
        if not gstin_rules.has_valid_format(value):
            issues.append(
                Issue(
                    "gstin",
                    "error",
                    (f"{party}.gstin",),
                    f"{party.title()} GSTIN {value} isn't 15 valid characters.",
                )
            )
        elif not gstin_rules.is_valid(value):
            issues.append(
                Issue(
                    "gstin",
                    "error",
                    (f"{party}.gstin",),
                    f"{party.title()} GSTIN {value} fails its checksum "
                    "(likely a misread character).",
                )
            )
    return issues


def check_tax_types(doc_type: str, data: Mapping[str, Any]) -> list[Issue]:
    currency = data.get("currency") or (data.get("total") or {}).get("currency")
    lines = data.get("taxes") or []
    if currency not in (None, "INR") or not lines:
        return []
    kinds = {line.get("type") for line in lines}
    issues = []
    if "IGST" in kinds and kinds & {"CGST", "SGST"}:
        issues.append(
            Issue(
                "tax_type",
                "warning",
                ("taxes",),
                "IGST is charged together with CGST/SGST; a supply is either inter-state "
                "(IGST) or intra-state (CGST + SGST).",
            )
        )
    if ("CGST" in kinds) != ("SGST" in kinds):
        issues.append(
            Issue("tax_type", "warning", ("taxes",), "CGST and SGST should appear together.")
        )
    return issues


def check_dates(doc_type: str, data: Mapping[str, Any], *, today: date) -> list[Issue]:
    field = DATE_FIELDS[doc_type]
    raw = data.get(field)
    if not raw:
        return []
    issued = date.fromisoformat(raw)
    issues = []
    if issued > today:
        issues.append(
            Issue("dates", "warning", (field,), f"The document date {issued} is in the future.")
        )
    if issued.year < 2000:
        issues.append(
            Issue("dates", "warning", (field,), f"The document date {issued} is implausibly old.")
        )
    later = LATER_FIELDS.get(doc_type)
    if later and data.get(later) and date.fromisoformat(data[later]) < issued:
        issues.append(
            Issue(
                "dates",
                "warning",
                (later, field),
                f"{later.replace('_', ' ').capitalize()} is before the document date.",
            )
        )
    return issues


@dataclass(frozen=True)
class WorkspaceLookups:
    """Questions only the workspace's other documents can answer (F6 AC1)."""

    find_duplicates: Callable[[str | None, str | None, str], Awaitable[list[str]]]
    vendor_seen: Callable[[str | None, str | None], Awaitable[bool]]


def party_of(doc_type: str, data: Mapping[str, Any]) -> Mapping[str, Any]:
    return (data.get("merchant") if doc_type == "receipt" else data.get("vendor")) or {}


def run_checks(doc_type: str, data: Mapping[str, Any], *, today: date) -> list[Issue]:
    """The checks that need nothing but the data."""
    return [
        *check_amount_format(doc_type, data),
        *check_line_items(doc_type, data),
        *check_totals(doc_type, data),
        *check_gstins(doc_type, data),
        *check_tax_types(doc_type, data),
        *check_dates(doc_type, data, today=today),
    ]


async def check_workspace(
    doc_type: str, data: Mapping[str, Any], lookups: WorkspaceLookups
) -> list[Issue]:
    """Duplicate and known-vendor checks against the workspace's other documents."""
    issues = []
    party = party_of(doc_type, data)
    number_field = NUMBER_FIELDS[doc_type]
    number = data.get(number_field)
    if number and (
        duplicates := await lookups.find_duplicates(party.get("gstin"), party.get("name"), number)
    ):
        issues.append(
            Issue(
                "duplicate",
                "warning",
                (number_field,),
                f"Possible duplicate of {len(duplicates)} other document(s) with number "
                f"{number} from the same vendor.",
            )
        )
    if (party.get("gstin") or party.get("name")) and not await lookups.vendor_seen(
        party.get("gstin"), party.get("name")
    ):
        issues.append(
            Issue(
                "known_vendor",
                "info",
                ("merchant" if doc_type == "receipt" else "vendor",),
                "First document from this vendor in the workspace.",
            )
        )
    return issues


async def all_checks(
    doc_type: str, data: Mapping[str, Any], *, today: date, lookups: WorkspaceLookups | None
) -> list[Issue]:
    issues = run_checks(doc_type, data, today=today)
    if lookups is not None:
        issues += await check_workspace(doc_type, data, lookups)
    return issues


def severity_score(issues: list[Issue]) -> int:
    """Lower is better: errors count 10, warnings 1 (F6 plan §2)."""
    return sum(10 if i.severity == "error" else 1 if i.severity == "warning" else 0 for i in issues)
