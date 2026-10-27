import copy
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from app.validation.checks import (
    WorkspaceLookups,
    all_checks,
    amounts_match,
    check_amount_format,
    check_dates,
    check_gstins,
    check_line_items,
    check_tax_types,
    check_totals,
    run_checks,
    severity_score,
)
from tests.support.samples import clean_invoice, sample_truth

TODAY = date(2026, 10, 26)


def test_clean_invoice_passes_everything() -> None:
    assert run_checks("invoice", clean_invoice(), today=TODAY) == []


@pytest.mark.parametrize(
    ("a", "b", "match"),
    [
        ("100.00", "100.99", True),
        ("100.00", "101.01", False),
        ("100000", "100499", True),
        ("100000", "100600", False),
    ],
)
def test_tolerance_is_one_rupee_or_half_a_percent(a: str, b: str, match: bool) -> None:
    assert amounts_match(Decimal(a), Decimal(b)) is match


def test_line_amount_that_doesnt_match_quantity_times_rate() -> None:
    data = clean_invoice()
    data["line_items"][1]["amount"]["amount"] = 5670.0  # 12 x 480 is 5760

    issues = check_line_items("invoice", data)

    assert [i.check for i in issues] == ["line_items", "line_items"]  # the line and the subtotal
    assert "line_items.1.amount.amount" in issues[0].paths
    assert all(i.fixable for i in issues)


def test_total_that_doesnt_add_up() -> None:
    data = clean_invoice()
    data["total"]["amount"] = 18626.8

    [issue] = check_totals("invoice", data)

    assert (issue.check, issue.severity) == ("totals", "error")
    assert issue.paths[0] == "total.amount"


def test_receipt_with_tax_included_in_prices_passes() -> None:
    data = copy.deepcopy(sample_truth("synthetic-receipt-001")["data"])
    data["total"]["amount"] = data["subtotal"]["amount"]  # tax shown, but already included

    assert check_totals("receipt", data) == []
    assert check_totals("invoice", {**clean_invoice(), "total": clean_invoice()["subtotal"]})


def test_receipt_totals_use_tax_total() -> None:
    data = copy.deepcopy(sample_truth("synthetic-receipt-001")["data"])
    assert check_totals("receipt", data) == []

    data["tax_total"]["amount"] = 0
    assert [i.check for i in check_totals("receipt", data)] == ["totals"]


def test_gstin_misread_digit_fails_checksum() -> None:
    data = clean_invoice()
    gstin = data["vendor"]["gstin"]
    data["vendor"]["gstin"] = gstin[:5] + ("X" if gstin[5] != "X" else "Y") + gstin[6:]

    [issue] = check_gstins("invoice", data)

    assert issue.paths == ("vendor.gstin",)
    assert "checksum" in issue.message
    assert issue.fixable


def test_missing_gstin_is_not_checked() -> None:
    data = clean_invoice()
    data["buyer"]["gstin"] = None

    assert check_gstins("invoice", data) == []


def test_igst_mixed_with_cgst_is_a_warning_not_fixable() -> None:
    data = clean_invoice()
    data["taxes"][1]["type"] = "IGST"

    issues = check_tax_types("invoice", data)

    assert {i.severity for i in issues} == {"warning"}
    assert not any(i.fixable for i in issues)


def test_foreign_currency_skips_gst_rules() -> None:
    data = clean_invoice()
    data["currency"] = "USD"
    data["taxes"][1]["type"] = "IGST"

    assert check_tax_types("invoice", data) == []


def test_dates() -> None:
    data = clean_invoice()
    assert check_dates("invoice", data, today=TODAY) == []

    data["invoice_date"] = "2027-01-01"
    data["due_date"] = "2026-12-01"
    messages = [i.message for i in check_dates("invoice", data, today=TODAY)]

    assert any("future" in m for m in messages)
    assert any("before the document date" in m for m in messages)


def test_no_line_items_skips_line_checks() -> None:
    data = clean_invoice()
    data["line_items"] = []
    data["subtotal"] = None

    assert check_line_items("invoice", data) == []
    assert check_totals("invoice", data) == []


async def test_duplicate_and_known_vendor_lookups() -> None:
    seen: list[tuple[Any, ...]] = []

    async def find_duplicates(gstin: str | None, name: str | None, number: str) -> list[str]:
        seen.append((gstin, name, number))
        return ["other-doc"]

    async def vendor_seen(_gstin: str | None, _name: str | None) -> bool:
        return False

    lookups = WorkspaceLookups(find_duplicates=find_duplicates, vendor_seen=vendor_seen)
    issues = await all_checks("invoice", clean_invoice(), today=TODAY, lookups=lookups)

    assert {(i.check, i.severity) for i in issues} == {
        ("duplicate", "warning"),
        ("known_vendor", "info"),
    }
    assert seen[0][2] == "SYN/2026-27/0142"


def test_severity_score() -> None:
    data = clean_invoice()
    data["total"]["amount"] = 1
    data["taxes"][1]["type"] = "IGST"

    issues = run_checks("invoice", data, today=TODAY)

    errors = sum(i.severity == "error" for i in issues)
    warnings = sum(i.severity == "warning" for i in issues)
    assert severity_score(issues) == 10 * errors + warnings
    assert errors >= 1
    assert warnings >= 1


def test_amount_with_three_decimals_looks_like_a_thousands_separator() -> None:
    receipt = {
        "line_items": [
            {"description": "TICKET", "amount": {"amount": Decimal("60.000"), "currency": "IDR"}}
        ],
        "subtotal": {"amount": Decimal("60.000"), "currency": "IDR"},
        "tax_total": {"amount": Decimal("5.455"), "currency": "IDR"},
        "total": {"amount": Decimal("60.000"), "currency": "IDR"},
    }

    issues = check_amount_format("receipt", receipt)

    assert [i.paths for i in issues] == [
        ("line_items.0.amount.amount",),
        ("subtotal.amount",),
        ("tax_total.amount",),
        ("total.amount",),
    ]
    assert all(i.fixable and i.severity == "error" for i in issues)


def test_two_decimals_and_whole_amounts_are_fine() -> None:
    assert check_amount_format("invoice", clean_invoice()) == []
    assert (
        check_amount_format("receipt", {"total": {"amount": Decimal("60000"), "currency": "IDR"}})
        == []
    )
    # Quantities may have three decimals (1.250 kg): only money is checked.
    assert (
        check_amount_format(
            "invoice", {"line_items": [{"quantity": Decimal("1.250"), "amount": None}]}
        )
        == []
    )


def test_taxes_larger_than_the_total_are_an_error_even_when_tax_is_included() -> None:
    receipt = {
        "subtotal": {"amount": Decimal("60.0"), "currency": "IDR"},
        "tax_total": {"amount": Decimal("5455"), "currency": "IDR"},
        "total": {"amount": Decimal("60.0"), "currency": "IDR"},
    }

    [issue] = check_totals("receipt", receipt)

    assert (issue.check, issue.severity, issue.fixable) == ("totals", "error", True)
    assert "more than the total" in issue.message
