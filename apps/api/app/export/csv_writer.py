"""CSV that spreadsheets open correctly and safely (F9 AC4, AC5)."""

import csv
import io
from collections.abc import Iterable
from decimal import Decimal

from app.export.rows import Cell

BOM = "﻿"  # so Excel reads UTF-8 (₹, non-English names)
# A cell starting with these may run as a formula in a spreadsheet (CSV injection).
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def _text(cell: Cell) -> str:
    if cell is None:
        return ""
    if isinstance(cell, Decimal):
        return format(cell, "f")  # plain decimal with a dot, never 1E+4
    if isinstance(cell, int):
        return str(cell)
    # Only text from documents is escaped; numbers (negative amounts too) stay numbers.
    return f"'{cell}" if cell.startswith(FORMULA_STARTS) else cell


def to_csv(rows: Iterable[list[Cell]], *, header: list[str] | None = None) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    if header is not None:
        buffer.write(BOM)
        writer.writerow(header)
    for row in rows:
        writer.writerow([_text(cell) for cell in row])
    return buffer.getvalue()
