import csv
import io
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.export.csv_writer import BOM, to_csv
from app.export.rows import (
    DOCUMENT_COLUMNS,
    LINE_COLUMNS,
    ExportedDocument,
    document_row,
    line_rows,
)
from tests.support.samples import sample_truth

INVOICE = sample_truth("synthetic-invoice-001")["data"]
RECEIPT = sample_truth("synthetic-receipt-001")["data"]


def exported(doc_type: str, data: dict[str, Any], **overrides: Any) -> ExportedDocument:
    values: dict[str, Any] = {
        "id": "d1",
        "filename": "x.pdf",
        "doc_type": doc_type,
        "status": "APPROVED",
        "approved_at": datetime(2026, 10, 27, 9, 30, tzinfo=UTC),
        "approved_by": "agent",
        "corrections": 0,
        "data": data,
    }
    return ExportedDocument(**{**values, **overrides})


def as_dict(doc_type: str, data: dict[str, Any]) -> dict[str, Any]:
    return dict(zip(DOCUMENT_COLUMNS, document_row(exported(doc_type, data)), strict=True))


def test_ac2_invoice_columns_and_tax_sums() -> None:
    row = as_dict("invoice", INVOICE)

    assert (row["number"], row["document_date"], row["vendor_name"]) == (
        "SYN/2026-27/0142",
        "2026-08-14",
        "Kaveri Fasteners Private Limited",
    )
    assert row["total"] == Decimal("16826.8")
    taxes = [row[c] for c in ("cgst", "sgst", "igst", "other_tax")]
    assert row["tax_total"] == sum(t for t in taxes if t is not None)
    assert (row["status"], row["approved_by"], row["approved_at"]) == (
        "APPROVED",
        "agent",
        "2026-10-27T09:30:00+00:00",
    )


def test_ac2_receipt_has_no_buyer_and_uses_its_tax_total() -> None:
    row = as_dict("receipt", RECEIPT)

    assert (row["buyer_name"], row["buyer_gstin"]) == (None, None)
    assert row["tax_total"] == Decimal(str(RECEIPT["tax_total"]["amount"]))
    assert row["vendor_name"] == RECEIPT["merchant"]["name"]


def test_ac2_line_items_link_back_to_their_document() -> None:
    rows = line_rows(exported("invoice", INVOICE))

    assert len(rows) == len(INVOICE["line_items"])
    first = dict(zip(LINE_COLUMNS, rows[0], strict=True))
    assert (first["document_id"], first["document_number"], first["line"]) == (
        "d1",
        "SYN/2026-27/0142",
        1,
    )


def test_ac4_ac5_bom_plain_decimals_and_no_formulas() -> None:
    text = to_csv(
        [['=HYPERLINK("x")', "+1", "@SUM", "-2", Decimal("-60000.00"), Decimal("1E+4"), "Ok"]],
        header=["a", "b", "c", "d", "e", "f", "g"],
    )

    assert text.startswith(BOM)
    [header, row] = list(csv.reader(io.StringIO(text.removeprefix(BOM))))
    assert header == ["a", "b", "c", "d", "e", "f", "g"]
    assert row == ['\'=HYPERLINK("x")', "'+1", "'@SUM", "'-2", "-60000.00", "10000", "Ok"]
