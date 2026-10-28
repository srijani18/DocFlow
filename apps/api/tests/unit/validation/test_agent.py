import copy
from datetime import date
from typing import Any

from app.validation.agent import Fix, run_agent
from app.validation.checks import Issue
from tests.support.samples import clean_invoice

TODAY = date(2026, 10, 26)
SCHEMA = "docflow/invoice/v1"


class FakeRereader:
    def __init__(self, *rounds: list[Fix]) -> None:
        self.rounds = list(rounds)
        self.calls: list[list[Issue]] = []

    async def reread(
        self, *, doc_type: str, issues: list[Issue], data: dict[str, Any]
    ) -> list[Fix]:
        self.calls.append(issues)
        return self.rounds.pop(0) if self.rounds else []


def misread_total() -> dict[str, Any]:
    data = clean_invoice()
    data["total"]["amount"] = 18826.8  # printed 16826.80; a 6 read as an 8
    return data


async def test_ac3_misread_total_is_fixed() -> None:
    rereader = FakeRereader([Fix("total.amount", 16826.8, 0.97, "8 was a 6")])

    result = await run_agent("invoice", SCHEMA, misread_total(), today=TODAY, rereader=rereader)

    assert result.data["total"]["amount"] == 16826.8
    assert result.issues == []
    assert [i.check for i in result.resolved] == ["totals"]
    assert result.rounds == 1
    assert result.changed


async def test_ac3_misread_gstin_is_fixed() -> None:
    data = clean_invoice()
    good = data["vendor"]["gstin"]
    data["vendor"]["gstin"] = good[:9] + ("8" if good[9] != "8" else "9") + good[10:]

    result = await run_agent(
        "invoice",
        SCHEMA,
        data,
        today=TODAY,
        rereader=FakeRereader([Fix("vendor.gstin", good, 0.9, "misread")]),
    )

    assert result.data["vendor"]["gstin"] == good
    assert result.issues == []


async def test_ac4_fix_that_makes_things_worse_is_discarded() -> None:
    worse = FakeRereader(
        [Fix("total.amount", 99999.0, 0.6, "guess"), Fix("subtotal.amount", 1.0, 0.6, "guess")]
    )
    original = misread_total()

    result = await run_agent(
        "invoice", SCHEMA, copy.deepcopy(original), today=TODAY, rereader=worse
    )

    assert result.data == original
    assert not result.changed
    assert [i.check for i in result.issues] == ["totals"]


async def test_ac4_no_progress_stops_after_one_round() -> None:
    rereader = FakeRereader([])

    result = await run_agent("invoice", SCHEMA, misread_total(), today=TODAY, rereader=rereader)

    assert result.rounds == 1
    assert len(rereader.calls) == 1
    assert not result.changed


async def test_ac4_at_most_two_rounds() -> None:
    data = misread_total()
    data["line_items"][0]["amount"]["amount"] = 5100.0  # also misread: 40 x 125 = 5000
    rereader = FakeRereader(
        [Fix("line_items.0.amount.amount", 5000.0, 0.9, "1 was a 0")],  # partial progress
        [Fix("total.amount", 16826.8, 0.9, "8 was a 6")],
        [Fix("nothing", 0, 0.9, "never asked")],
    )

    result = await run_agent("invoice", SCHEMA, data, today=TODAY, rereader=rereader)

    assert result.rounds == 2
    assert result.issues == []
    assert len(result.fixes) == 2


async def test_model_can_only_touch_fields_named_by_failed_checks() -> None:
    rereader = FakeRereader(
        [
            Fix("total.amount", 16826.8, 0.97, "ok"),
            Fix("vendor.name", "Someone Else", 0.99, "sneaky"),
        ]
    )

    result = await run_agent("invoice", SCHEMA, misread_total(), today=TODAY, rereader=rereader)

    assert result.data["vendor"]["name"] == "Kaveri Fasteners Private Limited"
    assert [f.path for f in result.fixes] == ["total.amount"]


async def test_ac5_non_fixable_issues_never_reach_the_model() -> None:
    data = clean_invoice()
    data["taxes"][1]["type"] = "IGST"
    rereader = FakeRereader()

    result = await run_agent("invoice", SCHEMA, data, today=TODAY, rereader=rereader)

    assert rereader.calls == []
    assert {i.check for i in result.issues} == {"tax_types"}


async def test_fix_that_breaks_the_schema_is_discarded() -> None:
    rereader = FakeRereader([Fix("total.amount", "sixteen thousand", 0.9, "words")])

    result = await run_agent("invoice", SCHEMA, misread_total(), today=TODAY, rereader=rereader)

    assert not result.changed
