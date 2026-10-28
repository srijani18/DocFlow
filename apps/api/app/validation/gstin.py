"""GSTIN format and checksum (F6 AC1).

A GSTIN is 15 characters: 2-digit state code, 10-character PAN, entity number, "Z", and a
check character. The check character is a mod-36 checksum over the first 14 characters with
alternating weights 1 and 2 (each product is split into quotient and remainder of 36).
"""

import re

PATTERN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def check_character(first14: str) -> str:
    total = 0
    for index, char in enumerate(first14):
        product = _CHARS.index(char) * (1 if index % 2 == 0 else 2)
        total += product // 36 + product % 36
    return _CHARS[(36 - total % 36) % 36]


def has_valid_format(value: str) -> bool:
    return PATTERN.match(value) is not None


def is_valid(value: str) -> bool:
    return has_valid_format(value) and check_character(value[:14]) == value[14]


def with_valid_checksum(first14: str) -> str:
    """Completes 14 characters into a valid GSTIN (for synthetic test data)."""
    return first14 + check_character(first14)
