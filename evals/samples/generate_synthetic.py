"""Generates synthetic sample documents and their ground truth (F5 spec D4).

Every name, GSTIN and amount here is invented. Free LLM tiers may keep what they receive,
so only documents like these (or public datasets) are ever uploaded (constitution §5.5).

    cd apps/api && uv run python ../../evals/samples/generate_synthetic.py

Writes <name>.pdf and <name>.json (the expected extraction) next to this script.
"""

import json
from decimal import Decimal
from pathlib import Path

from fpdf import FPDF

OUT = Path(__file__).parent
TWO = Decimal("0.01")


def money(amount: Decimal | None) -> dict[str, object] | None:
    return None if amount is None else {"amount": float(amount), "currency": "INR"}


def address(line1: str, city: str, state: str, pin: str) -> dict[str, str | None]:
    return {"line1": line1, "line2": None, "city": city, "state": state, "postal_code": pin, "country": "India"}


class Doc(FPDF):
    def __init__(self) -> None:
        super().__init__(format="A4")
        self.set_auto_page_break(auto=True, margin=15)
        self.add_page()
        self.set_font("Helvetica", size=10)

    def line(self, text: str = "", *, bold: bool = False, size: int = 10) -> None:  # type: ignore[override]
        self.set_font("Helvetica", "B" if bold else "", size)
        self.cell(0, 6, text, new_x="LMARGIN", new_y="NEXT")

    def table(self, headers: list[str], rows: list[list[str]], widths: list[int]) -> None:
        self.set_font("Helvetica", "B", 9)
        for header, width in zip(headers, widths, strict=True):
            self.cell(width, 7, header, border=1)
        self.ln()
        self.set_font("Helvetica", "", 9)
        for row in rows:
            for value, width in zip(row, widths, strict=True):
                self.cell(width, 7, value, border=1)
            self.ln()


def invoice_001() -> None:
    items = [
        ("Steel brackets, galvanised", "7326", Decimal(40), Decimal("125.00")),
        ("Hex bolts M10 (box of 100)", "7318", Decimal(12), Decimal("480.00")),
        ("Installation service", "998719", Decimal(1), Decimal("3500.00")),
    ]
    lines = [(d, h, q, p, (q * p).quantize(TWO)) for d, h, q, p in items]
    subtotal = sum((amount for *_, amount in lines), Decimal(0))
    cgst = (subtotal * Decimal("0.09")).quantize(TWO)
    sgst = cgst
    total = subtotal + cgst + sgst

    pdf = Doc()
    pdf.line("TAX INVOICE", bold=True, size=16)
    pdf.line("Invoice No: SYN/2026-27/0142")
    pdf.line("Invoice Date: 14-08-2026        Due Date: 13-09-2026")
    pdf.ln(2)
    pdf.line("Seller: Kaveri Fasteners Private Limited", bold=True)
    pdf.line("Plot 17, Peenya Industrial Area, Bengaluru, Karnataka 560058")
    pdf.line("GSTIN: 29ABCDE1234F1Z5")
    pdf.ln(2)
    pdf.line("Bill to: Sahyadri Build Works LLP", bold=True)
    pdf.line("44 MG Road, Mysuru, Karnataka 570001")
    pdf.line("GSTIN: 29PQRSX6789K1Z2        Place of supply: Karnataka")
    pdf.ln(3)
    pdf.table(
        ["Description", "HSN/SAC", "Qty", "Rate (INR)", "Amount (INR)"],
        [[d, h, str(q), f"{p:,.2f}", f"{a:,.2f}"] for d, h, q, p, a in lines],
        [70, 25, 15, 35, 40],
    )
    pdf.ln(2)
    pdf.line(f"Taxable value: INR {subtotal:,.2f}")
    pdf.line(f"CGST @ 9%: INR {cgst:,.2f}")
    pdf.line(f"SGST @ 9%: INR {sgst:,.2f}")
    pdf.line(f"Grand Total: INR {total:,.2f}", bold=True)
    pdf.ln(4)
    pdf.line("Synthetic document generated for DocFlow testing. Not a real invoice.", size=8)
    pdf.output(str(OUT / "synthetic-invoice-001.pdf"))

    truth = {
        "doc_type": "invoice",
        "schema_id": "docflow/invoice/v1",
        "data": {
            "invoice_number": "SYN/2026-27/0142",
            "invoice_date": "2026-08-14",
            "due_date": "2026-09-13",
            "vendor": {
                "name": "Kaveri Fasteners Private Limited",
                "gstin": "29ABCDE1234F1Z5",
                "address": address("Plot 17, Peenya Industrial Area", "Bengaluru", "Karnataka", "560058"),
            },
            "buyer": {
                "name": "Sahyadri Build Works LLP",
                "gstin": "29PQRSX6789K1Z2",
                "address": address("44 MG Road", "Mysuru", "Karnataka", "570001"),
            },
            "place_of_supply": "Karnataka",
            "currency": "INR",
            "line_items": [
                {"description": d, "hsn_sac": h, "quantity": float(q), "unit_price": money(p), "amount": money(a)}
                for d, h, q, p, a in lines
            ],
            "subtotal": money(subtotal),
            "taxes": [
                {"type": "CGST", "rate_percent": 9, "amount": money(cgst)},
                {"type": "SGST", "rate_percent": 9, "amount": money(sgst)},
            ],
            "total": money(total),
        },
    }
    (OUT / "synthetic-invoice-001.json").write_text(json.dumps(truth, indent=2) + "\n")


def receipt_001() -> None:
    pdf = Doc()
    pdf.line("ANNAPURNA TIFFIN CENTRE", bold=True, size=14)
    pdf.line("12 Gandhi Bazaar, Bengaluru, Karnataka 560004")
    pdf.line("GSTIN: 29LMNOP4321Q1Z9")
    pdf.line("Bill No: 88231      Date: 02/09/2026      Time: 13:42")
    pdf.ln(2)
    rows = [("Masala dosa", 2, Decimal("90.00")), ("Filter coffee", 2, Decimal("40.00")), ("Idli vada", 1, Decimal("70.00"))]
    pdf.table(["Item", "Qty", "Amount"], [[i, str(q), f"{a * q:,.2f}"] for i, q, a in rows], [90, 20, 40])
    subtotal = sum((a * q for _, q, a in rows), Decimal(0))
    tax = (subtotal * Decimal("0.05")).quantize(TWO)
    pdf.ln(2)
    pdf.line(f"Subtotal: {subtotal:,.2f}")
    pdf.line(f"GST 5%: {tax:,.2f}")
    pdf.line(f"TOTAL PAID: INR {subtotal + tax:,.2f}   (UPI)", bold=True)
    pdf.line("Synthetic receipt generated for DocFlow testing.", size=8)
    pdf.output(str(OUT / "synthetic-receipt-001.pdf"))

    truth = {
        "doc_type": "receipt",
        "schema_id": "docflow/receipt/v1",
        "data": {
            "receipt_number": "88231",
            "date": "2026-09-02",
            "time": "13:42",
            "merchant": {
                "name": "Annapurna Tiffin Centre",
                "gstin": "29LMNOP4321Q1Z9",
                "address": address("12 Gandhi Bazaar", "Bengaluru", "Karnataka", "560004"),
            },
            "currency": "INR",
            "line_items": [{"description": i, "quantity": q, "amount": money(a * q)} for i, q, a in rows],
            "subtotal": money(subtotal),
            "tax_total": money(tax),
            "total": money(subtotal + tax),
            "payment_method": "UPI",
        },
    }
    (OUT / "synthetic-receipt-001.json").write_text(json.dumps(truth, indent=2) + "\n")


def other_001() -> None:
    pdf = Doc()
    pdf.line("Notice of office relocation", bold=True, size=14)
    pdf.ln(2)
    for text in (
        "Dear customer,",
        "From 1 November 2026 our office moves to 9 Residency Road, Bengaluru.",
        "Phone numbers and email addresses stay the same.",
        "Regards, Kaveri Fasteners (synthetic letter for DocFlow testing)",
    ):
        pdf.line(text)
    pdf.output(str(OUT / "synthetic-other-001.pdf"))
    (OUT / "synthetic-other-001.json").write_text(json.dumps({"doc_type": "other"}, indent=2) + "\n")


if __name__ == "__main__":
    invoice_001()
    receipt_001()
    other_001()
    print(f"wrote samples to {OUT}")
