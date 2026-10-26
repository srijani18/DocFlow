import copy
from typing import Any

import pytest

from app.schemas_registry import bundle
from evals.scoring import matches, score
from tests.support.samples import sample_truth

INVOICE = sample_truth("synthetic-invoice-001")["data"]
SCHEMA = bundle("docflow/invoice/v1")


def wrong_paths(predicted: dict[str, Any], **kwargs: Any) -> list[str]:
    return [r.path for r in score(SCHEMA, INVOICE, predicted, **kwargs) if not r.correct]


def test_perfect_prediction_scores_every_field_correct() -> None:
    results = score(SCHEMA, INVOICE, copy.deepcopy(INVOICE))

    assert all(r.correct for r in results)
    assert len(results) > 30
    assert {r.rule for r in results} >= {"exact", "fuzzy", "numeric:0.01"}


def test_ac2_exact_normalises_whitespace_and_nfc() -> None:
    assert matches("exact", "SYN/2026-27/0142", "  SYN/2026-27/0142 ")
    assert matches("exact", "Café", "Café")  # NFD vs NFC
    assert not matches("exact", "SYN/2026-27/0142", "syn/2026-27/0142")


def test_ac2_fuzzy_threshold() -> None:
    assert matches("fuzzy", "Kaveri Fasteners Private Limited", "KAVERI FASTENERS PVT LIMITED")
    assert not matches("fuzzy", "Kaveri Fasteners Private Limited", "Godavari Electricals")
    assert matches("fuzzy", "Kaveri Fasteners Private Limited", "kaveri  fasteners private limited")
    assert matches("fuzzy", "Plot 17, Peenya Industrial Area", "Plot 17 Peenya Industrial Area")


def test_ac2_numeric_tolerance() -> None:
    assert matches("numeric:0.01", 16826.8, "16826.81")
    assert not matches("numeric:0.01", 16826.8, 16826.82)
    assert not matches("numeric:0.01", 16826.8, "about 16k")


def test_ac2_nulls_must_match() -> None:
    assert matches("exact", None, None)
    assert not matches("exact", None, "2026-09-13")
    assert not matches("numeric:0.01", 100, None)


def test_ac2_line_items_by_index() -> None:
    predicted = copy.deepcopy(INVOICE)
    predicted["line_items"][1]["quantity"] = 13
    predicted["line_items"].pop()  # third item missing
    predicted["line_items"].append(
        {
            "description": "Bonus line",
            "hsn_sac": None,
            "quantity": 1,
            "unit_price": None,
            "amount": None,
        }
    )

    wrong = wrong_paths(predicted)

    assert "line_items.1.quantity" in wrong
    assert "line_items.2.description" in wrong  # compared with the extra line at index 2
    assert "line_items.0.quantity" not in wrong


def test_extra_items_count_as_wrong() -> None:
    predicted = copy.deepcopy(INVOICE)
    predicted["taxes"].append(
        {"type": "CESS", "rate_percent": 1, "amount": {"amount": 10, "currency": "INR"}}
    )

    assert {"taxes.2.type", "taxes.2.amount.amount"} <= set(wrong_paths(predicted))


def test_ac2_unlabelled_paths_skipped() -> None:
    predicted = copy.deepcopy(INVOICE)
    predicted["vendor"]["gstin"] = "WRONG"
    predicted["line_items"][0]["amount"]["currency"] = "USD"

    results = score(
        SCHEMA,
        INVOICE,
        predicted,
        unlabelled=["vendor", "vendor.*", "line_items.*.amount.currency"],
    )

    paths = {r.path for r in results}
    assert not any(p.startswith("vendor") for p in paths)
    assert "line_items.0.amount.currency" not in paths
    assert all(r.correct for r in results)


def test_generic_paths_for_aggregation() -> None:
    [result] = [
        r for r in score(SCHEMA, INVOICE, INVOICE) if r.path == "line_items.2.amount.amount"
    ]

    assert result.generic_path == "line_items.*.amount.amount"


@pytest.mark.parametrize("predicted", [None, {}, {"line_items": "oops"}])
def test_missing_or_malformed_prediction_scores_wrong_not_crash(predicted: Any) -> None:
    results = score(SCHEMA, INVOICE, predicted)

    assert results
    assert not all(r.correct for r in results)
