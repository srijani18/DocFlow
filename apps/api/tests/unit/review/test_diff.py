from decimal import Decimal

from app.review.diff import Change, diff, exact


def test_ac4_scalar_and_nested_changes_by_path() -> None:
    old = {"invoice_number": "A-1", "vendor": {"name": "Kaveri", "gstin": "X"}, "due_date": None}
    new = {
        "invoice_number": "A-1",
        "vendor": {"name": "Kaveri Ltd", "gstin": "X"},
        "due_date": "2026-09-13",
    }

    assert diff(old, new) == [
        Change("vendor.name", "Kaveri", "Kaveri Ltd"),
        Change("due_date", None, "2026-09-13"),
    ]


def test_ac4_line_items_added_and_removed_by_position() -> None:
    row = {"description": "Bolts", "amount": {"amount": Decimal("10.00"), "currency": "INR"}}
    other = {"description": "Nuts", "amount": {"amount": Decimal("5.00"), "currency": "INR"}}

    assert diff({"line_items": [row]}, {"line_items": [row, other]}) == [
        Change("line_items.1", None, other)
    ]
    assert diff({"line_items": [row, other]}, {"line_items": [other]}) == [
        Change("line_items.0.description", "Bolts", "Nuts"),
        Change("line_items.0.amount.amount", Decimal("10.00"), Decimal("5.00")),
        Change("line_items.1", other, None),
    ]


def test_numbers_compare_by_value_not_type() -> None:
    assert diff({"total": Decimal("16826.80")}, {"total": 16826.8}) == []
    assert diff({"quantity": 2}, {"quantity": 2.0}) == []
    assert diff({"flag": True}, {"flag": 1}) == [Change("flag", True, 1)]


def test_cleared_field_is_a_change_to_null() -> None:
    assert diff({"po_number": "PO-1"}, {"po_number": None}) == [Change("po_number", "PO-1", None)]


def test_exact_turns_floats_into_the_decimals_sent() -> None:
    assert exact({"total": {"amount": 16826.8}, "items": [0.1, 3]}) == {
        "total": {"amount": Decimal("16826.8")},
        "items": [Decimal("0.1"), 3],
    }
