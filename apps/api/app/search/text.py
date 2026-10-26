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
