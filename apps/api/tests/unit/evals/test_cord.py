from decimal import Decimal

import pytest

from evals.cord import map_ground_truth, parse_amount


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("60.000", Decimal(60000)),
        ("60,000", Decimal(60000)),
        ("Rp 1.250.000,-", Decimal(1250000)),
        ("", None),
        (None, None),
        ("-", None),
    ],
)
def test_rupiah_amounts(raw: object, expected: Decimal | None) -> None:
    assert parse_amount(raw) == expected


def test_cord_labels_map_to_receipt_v1() -> None:
    gt = {
        "menu": [
            {"nm": "-TICKET CP", "cnt": "2", "price": "60.000"},
            {"nm": "ICE TEA", "cnt": "1x", "price": "8,000"},
        ],
        "sub_total": {"subtotal_price": "68.000", "tax_price": "6.800"},
        "total": {"total_price": "74.800"},
    }

    truth = map_ground_truth(gt)

    assert truth["line_items"] == [
        {
            "description": "-TICKET CP",
            "quantity": 2.0,
            "amount": {"amount": 60000.0, "currency": "IDR"},
        },
        {
            "description": "ICE TEA",
            "quantity": 1.0,
            "amount": {"amount": 8000.0, "currency": "IDR"},
        },
    ]
    assert truth["total"] == {"amount": 74800.0, "currency": "IDR"}
    assert truth["tax_total"]["amount"] == 6800.0
    assert truth["merchant"] is None


def test_single_menu_item_given_as_an_object() -> None:
    truth = map_ground_truth(
        {
            "menu": {"nm": "COFFEE", "cnt": "1", "price": "20.000"},
            "total": {"total_price": "20.000"},
        }
    )

    assert [item["description"] for item in truth["line_items"]] == ["COFFEE"]
    assert truth["subtotal"] is None
