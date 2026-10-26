"""Field-level differences between two extraction instances (F7 AC4).

Paths are dotted with zero-based indices, as everywhere else. Objects are compared key by
key and lists by position: a row added at the end is one change at `line_items.3` (old
null); a row removed is one change with new null.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class Change:
    path: str
    old: Any
    new: Any


def exact(value: Any) -> Any:
    """Floats from a parsed request body as Decimals. A JSON number parsed to a float prints
    back as its shortest form, so `Decimal(str(f))` is the number the client sent."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: exact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [exact(item) for item in value]
    return value


def _same(old: Any, new: Any) -> bool:
    if isinstance(old, bool) or isinstance(new, bool):
        return old is new
    if isinstance(old, int | float | Decimal) and isinstance(new, int | float | Decimal):
        return Decimal(str(old)) == Decimal(str(new))
    return bool(old == new)


def diff(old: Any, new: Any, path: str = "") -> list[Change]:
    if isinstance(old, dict) and isinstance(new, dict):
        changes = []
        for key in [*old, *(k for k in new if k not in old)]:
            child = f"{path}.{key}" if path else key
            changes += diff(old.get(key), new.get(key), child)
        return changes
    if isinstance(old, list) and isinstance(new, list):
        changes = []
        for index in range(max(len(old), len(new))):
            child = f"{path}.{index}" if path else str(index)
            changes += diff(
                old[index] if index < len(old) else None,
                new[index] if index < len(new) else None,
                child,
            )
        return changes
    return [] if _same(old, new) else [Change(path, old, new)]
