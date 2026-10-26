"""Scores extracted fields against ground truth by each field's `x-eval` rule (F11 AC2).

- exact: equal after trimming and Unicode NFC (numbers compared as Decimals)
- fuzzy: difflib ratio >= 0.85 after case-folding and collapsing whitespace (spec D5)
- numeric:<tolerance>: |expected - actual| <= tolerance

Fields come from walking the truth; line items are compared by position. Paths are dotted
with zero-based indices (`line_items.0.amount.amount`), like the confidence paths.
"""

import fnmatch
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from typing import Any

FUZZY_THRESHOLD = 0.85
_INDEX = re.compile(r"\.\d+(?=\.|$)")


@dataclass(frozen=True)
class FieldResult:
    path: str
    rule: str
    expected: Any
    actual: Any
    correct: bool

    @property
    def generic_path(self) -> str:
        """`line_items.2.amount.amount` → `line_items.*.amount.amount` (for aggregation)."""
        return _INDEX.sub(".*", self.path)


def _subschema(schema: dict[str, Any], key: str | int) -> dict[str, Any]:
    for option in schema.get("anyOf", []):  # nullable objects and enums
        if isinstance(key, int) and "items" in option:
            return dict(option["items"])
        if isinstance(key, str) and key in option.get("properties", {}):
            return dict(option["properties"][key])
    if isinstance(key, int):
        return dict(schema.get("items", {}))
    return dict(schema.get("properties", {}).get(key, {}))


def _rule(schema: dict[str, Any]) -> str:
    if "x-eval" in schema:
        return str(schema["x-eval"])
    for option in schema.get("anyOf", []):
        if "x-eval" in option:
            return str(option["x-eval"])
    return "exact"


def _number(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _text(value: Any) -> str:
    return unicodedata.normalize("NFC", str(value)).strip()


def matches(rule: str, expected: Any, actual: Any) -> bool:
    if expected is None or actual is None:
        return expected is None and actual is None
    if rule.startswith("numeric:"):
        tolerance = Decimal(rule.split(":", 1)[1])
        left, right = _number(expected), _number(actual)
        return left is not None and right is not None and abs(left - right) <= tolerance
    if rule == "fuzzy":
        left_text = " ".join(_text(expected).casefold().split())
        right_text = " ".join(_text(actual).casefold().split())
        return SequenceMatcher(None, left_text, right_text).ratio() >= FUZZY_THRESHOLD
    left_number, right_number = _number(expected), _number(actual)
    if left_number is not None and right_number is not None:
        return left_number == right_number
    return _text(expected) == _text(actual)


def _masked(path: str, unlabelled: list[str]) -> bool:
    generic = _INDEX.sub(".*", path)
    return any(
        fnmatch.fnmatchcase(generic, pattern) or fnmatch.fnmatchcase(path, pattern)
        for pattern in unlabelled
    )


def score(
    schema: dict[str, Any], truth: Any, predicted: Any, *, unlabelled: list[str] | None = None
) -> list[FieldResult]:
    """One result per labelled leaf in the truth, plus every leaf of extra predicted items."""
    results: list[FieldResult] = []
    _walk(schema, truth, predicted, "", unlabelled=unlabelled or [], results=results)
    return results


def _walk(
    schema: dict[str, Any],
    expected: Any,
    actual: Any,
    path: str,
    *,
    unlabelled: list[str],
    results: list[FieldResult],
) -> None:
    if path and _masked(path, unlabelled):
        return
    if isinstance(expected, dict):
        actual_dict = actual if isinstance(actual, dict) else {}
        for key, value in expected.items():
            child = f"{path}.{key}" if path else key
            _walk(
                _subschema(schema, key),
                value,
                actual_dict.get(key),
                child,
                unlabelled=unlabelled,
                results=results,
            )
        return
    if isinstance(expected, list):
        actual_list = actual if isinstance(actual, list) else []
        item_schema = _subschema(schema, 0)
        for index, value in enumerate(expected):
            other = actual_list[index] if index < len(actual_list) else None
            _walk(
                item_schema, value, other, f"{path}.{index}", unlabelled=unlabelled, results=results
            )
        for index in range(len(expected), len(actual_list)):  # extra items are wrong
            _walk_extra(item_schema, actual_list[index], f"{path}.{index}", unlabelled, results)
        return
    results.append(
        FieldResult(path, _rule(schema), expected, actual, matches(_rule(schema), expected, actual))
    )


def _walk_extra(
    schema: dict[str, Any],
    actual: Any,
    path: str,
    unlabelled: list[str],
    results: list[FieldResult],
) -> None:
    if _masked(path, unlabelled):
        return
    if isinstance(actual, dict):
        for key, value in actual.items():
            _walk_extra(_subschema(schema, key), value, f"{path}.{key}", unlabelled, results)
        return
    results.append(FieldResult(path, _rule(schema), None, actual, actual is None))
