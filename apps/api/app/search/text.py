"""The words a document is found by, and the query that finds them (F8 AC2).

Punctuation becomes spaces on both sides, so "INV/2026-27/0142" is the words inv, 2026, 27
and 0142 whichever way it's typed. Values containing digits are also stored squashed
("inv2026270142", a GSTIN typed with spaces), and a query is also tried squashed.
"""

import re
from decimal import Decimal
from typing import Any

_SEPARATORS = re.compile(r"[^0-9A-Za-z]+")
_WORDS = re.compile(r"[0-9a-z]+")
SHORTEST_PREFIX = 2


def _leaves(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [leaf for child in value.values() for leaf in _leaves(child)]
    if isinstance(value, list):
        return [leaf for child in value for leaf in _leaves(child)]
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, float | Decimal):
        return [f"{Decimal(str(value)):.2f}"]
    return [str(value)]


def search_terms(data: dict[str, Any]) -> str:
    """Every value of the extraction as searchable words."""
    words = []
    for leaf in _leaves(data):
        spaced = _SEPARATORS.sub(" ", leaf).strip()
        if not spaced:
            continue
        words.append(spaced)
        squashed = spaced.replace(" ", "")
        if squashed != spaced and any(ch.isdigit() for ch in squashed):
            words.append(squashed)
    return " ".join(words)


def to_tsquery(query: str) -> str | None:
    """A prefix query for Postgres `to_tsquery('simple', …)`: every word, or the whole query
    squashed. None when there's nothing worth matching."""
    words = _WORDS.findall(query.lower())
    if not words or sum(map(len, words)) < SHORTEST_PREFIX:
        return None
    all_words = " & ".join(f"{word}:*" for word in words)
    if len(words) == 1:
        return all_words
    return f"({all_words}) | {''.join(words)}:*"


MAX_SNIPPET_FIELDS = 2
SQUASHED_MINIMUM = 4  # characters, so "ab" doesn't match inside every value


def _labelled_leaves(value: Any, path: str = "") -> list[tuple[str, str]]:
    if isinstance(value, dict):
        return [
            leaf
            for key, child in value.items()
            for leaf in _labelled_leaves(child, f"{path}.{key}" if path else str(key))
        ]
    if isinstance(value, list):
        return [
            leaf
            for index, child in enumerate(value)
            for leaf in _labelled_leaves(child, f"{path}.{index}")
        ]
    if value is None or isinstance(value, bool):
        return []
    return [(path, str(value))]


def _label(path: str) -> str:
    """line_items.1.description → "Line items 2 > Description"."""
    parts: list[str] = []
    for part in path.split("."):
        if part.isdigit() and parts:
            parts[-1] += f" {int(part) + 1}"  # the row number belongs to its table
        else:
            parts.append(part.replace("_", " ").capitalize())
    text = " > ".join(parts)
    return text.replace("Gstin", "GSTIN")


def snippet(data: dict[str, Any], query: str) -> str | None:
    """Up to two fields whose value matches every word of the query (or the query squashed),
    as "Label: [[value]]", for a person to see why a document matched (AC1)."""
    words = _WORDS.findall(query.lower())
    if not words:
        return None
    squashed = "".join(words)
    found = []
    for path, value in _labelled_leaves(data):
        value_words = _WORDS.findall(value.lower())
        joined = "".join(value_words)
        if all(any(v.startswith(w) for v in value_words) for w in words) or (
            len(squashed) >= SQUASHED_MINIMUM and squashed in joined
        ):
            found.append(f"{_label(path)}: [[{value}]]")
        if len(found) == MAX_SNIPPET_FIELDS:
            break
    return " · ".join(found) or None
