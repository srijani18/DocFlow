"""Synthetic Indian invoices, receipts and purchase orders with exact ground truth (F11 D1).

Every name, GSTIN, address and amount is invented. Documents are deterministic for a seed,
so rebuilding the dataset gives the same files and truth.
"""

import io
import random
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pypdfium2 as pdfium
from fpdf import FPDF
from PIL import Image, ImageFilter

TWO = Decimal("0.01")


@dataclass(frozen=True)
class Party:
    name: str
    gstin: str
    line1: str
    city: str
    state: str
    pin: str
    state_code: str


SELLERS = [
    Party(
        "Kaveri Fasteners Private Limited",
        "29ABCDE1234F1Z5",
        "Plot 17, Peenya Industrial Area",
        "Bengaluru",
        "Karnataka",
        "560058",
        "29",
    ),
    Party(
        "Narmada Office Supplies LLP",
        "24KLMNO6789P1Z3",
        "Shop 4, Ashram Road",
        "Ahmedabad",
        "Gujarat",
        "380009",
        "24",
    ),
    Party(
        "Godavari Electricals",
        "36PQRST2345U1Z8",
        "12-3-45, Begumpet",
        "Hyderabad",
        "Telangana",
        "500016",
        "36",
    ),
    Party(
        "Yamuna Packaging Industries",
        "07FGHIJ5678K1Z1",
        "B-22, Okhla Phase II",
        "New Delhi",
        "Delhi",
        "110020",
        "07",
    ),
    Party(
        "Tapti Textiles Private Limited",
        "27UVWXY9012Z1Z4",
        "88 Bhiwandi Road",
        "Thane",
        "Maharashtra",
        "421302",
        "27",
    ),
]
BUYERS = [
    Party(
        "Sahyadri Build Works LLP",
        "29PQRSX6789K1Z2",
        "44 MG Road",
        "Mysuru",
        "Karnataka",
        "570001",
        "29",
    ),
    Party(
        "Konkan Retail Private Limited",
        "27ABCPQ1234R1Z6",
        "7 Linking Road",
        "Mumbai",
        "Maharashtra",
        "400050",
        "27",
    ),
    Party(
        "Deccan Logistics",
        "36LMNPQ4567S1Z9",
        "Plot 9, Shamshabad",
        "Hyderabad",
        "Telangana",
        "501218",
        "36",
    ),
]
MERCHANTS = [
    Party(
        "ANNAPURNA TIFFIN CENTRE",
        "29LMNOP4321Q1Z9",
        "12 Gandhi Bazaar",
        "Bengaluru",
        "Karnataka",
        "560004",
        "29",
    ),
    Party(
        "CHAI POINT EXPRESS",
        "07QWERT5678Y1Z2",
        "Connaught Place, Block A",
        "New Delhi",
        "Delhi",
        "110001",
        "07",
    ),
    Party(
        "SAGAR STATIONERS",
        "24ZXCVB1234N1Z7",
        "Law Garden Road",
        "Ahmedabad",
        "Gujarat",
        "380006",
        "24",
    ),
]
ITEMS = [
    ("Steel brackets, galvanised", "7326", Decimal("125.00")),
    ("Hex bolts M10 (box of 100)", "7318", Decimal("480.00")),
    ("Installation service", "998719", Decimal("3500.00")),
    ("A4 copier paper (ream)", "4802", Decimal("265.00")),
    ("LED panel light 18W", "9405", Decimal("899.00")),
    ("Corrugated boxes 18x12x12", "4819", Decimal("42.50")),
    ("Cotton fabric (metre)", "5208", Decimal("185.00")),
    ("Annual maintenance contract", "998713", Decimal("12000.00")),
]
FOOD = [
    ("Masala dosa", Decimal("90.00")),
    ("Filter coffee", Decimal("40.00")),
    ("Idli vada", Decimal("70.00")),
    ("Ginger chai", Decimal("30.00")),
    ("Veg sandwich", Decimal("85.00")),
    ("Notebook 200 pages", Decimal("60.00")),
    ("Gel pens (pack of 5)", Decimal("50.00")),
]


def _money(amount: Decimal | None) -> dict[str, Any] | None:
    return None if amount is None else {"amount": float(amount), "currency": "INR"}


def _party(p: Party) -> dict[str, Any]:
    return {
        "name": p.name,
        "gstin": p.gstin,
        "address": {
            "line1": p.line1,
            "line2": None,
            "city": p.city,
            "state": p.state,
            "postal_code": p.pin,
            "country": "India",
        },
    }


class _Doc(FPDF):
    def __init__(self) -> None:
        super().__init__(format="A4")
        self.set_auto_page_break(auto=True, margin=15)
        self.add_page()

    def text_line(self, text: str, *, bold: bool = False, size: int = 10) -> None:
        self.set_font("Helvetica", "B" if bold else "", size)
        self.cell(0, 6, text, new_x="LMARGIN", new_y="NEXT")

    def grid(self, headers: list[str], rows: list[list[str]], widths: list[int]) -> None:
        self.set_font("Helvetica", "B", 9)
        for header, width in zip(headers, widths, strict=True):
            self.cell(width, 7, header, border=1)
        self.ln()
        self.set_font("Helvetica", "", 9)
        for row in rows:
            for value, width in zip(row, widths, strict=True):
                self.cell(width, 7, value, border=1)
            self.ln()


def _date(rng: random.Random) -> tuple[str, str]:
    month, day = rng.randint(4, 9), rng.randint(1, 28)
    return f"2026-{month:02d}-{day:02d}", f"{day:02d}-{month:02d}-2026"


def _tax_lines(
    subtotal: Decimal, same_state: bool, rate: Decimal
) -> list[tuple[str, Decimal, Decimal]]:
    if same_state:
        half = (subtotal * rate / 2 / 100).quantize(TWO)
        return [("CGST", rate / 2, half), ("SGST", rate / 2, half)]
    return [("IGST", rate, (subtotal * rate / 100).quantize(TWO))]


def _lines(rng: random.Random) -> list[tuple[str, str, Decimal, Decimal, Decimal]]:
    picked = rng.sample(ITEMS, rng.randint(2, 4))
    return [
        (d, h, Decimal(q), p, (Decimal(q) * p).quantize(TWO))
        for d, h, p in picked
        for q in [rng.randint(1, 24)]
    ]


def invoice(seed: int) -> tuple[bytes, dict[str, Any]]:
    rng = random.Random(seed)
    seller, buyer = rng.choice(SELLERS), rng.choice(BUYERS)
    iso, printed = _date(rng)
    number = f"INV/{rng.randint(2025, 2026)}-{rng.randint(10, 99)}/{rng.randint(100, 9999):04d}"
    lines = _lines(rng)
    subtotal = sum((line[4] for line in lines), Decimal(0))
    taxes = _tax_lines(
        subtotal, seller.state_code == buyer.state_code, Decimal(rng.choice([12, 18]))
    )
    total = subtotal + sum((t[2] for t in taxes), Decimal(0))

    pdf = _Doc()
    pdf.text_line("TAX INVOICE", bold=True, size=16)
    pdf.text_line(f"Invoice No: {number}")
    pdf.text_line(f"Invoice Date: {printed}")
    pdf.ln(2)
    pdf.text_line(f"Seller: {seller.name}", bold=True)
    pdf.text_line(f"{seller.line1}, {seller.city}, {seller.state} {seller.pin}")
    pdf.text_line(f"GSTIN: {seller.gstin}")
    pdf.ln(2)
    pdf.text_line(f"Bill to: {buyer.name}", bold=True)
    pdf.text_line(f"{buyer.line1}, {buyer.city}, {buyer.state} {buyer.pin}")
    pdf.text_line(f"GSTIN: {buyer.gstin}        Place of supply: {buyer.state}")
    pdf.ln(3)
    pdf.grid(
        ["Description", "HSN/SAC", "Qty", "Rate (INR)", "Amount (INR)"],
        [[d, h, str(q), f"{p:,.2f}", f"{a:,.2f}"] for d, h, q, p, a in lines],
        [70, 25, 15, 35, 40],
    )
    pdf.ln(2)
    pdf.text_line(f"Taxable value: INR {subtotal:,.2f}")
    for kind, rate, amount in taxes:
        pdf.text_line(f"{kind} @ {rate.normalize()}%: INR {amount:,.2f}")
    pdf.text_line(f"Grand Total: INR {total:,.2f}", bold=True)
    pdf.text_line("Synthetic document generated for DocFlow evals. Not a real invoice.", size=8)

    truth = {
        "invoice_number": number,
        "invoice_date": iso,
        "due_date": None,  # not printed on these invoices
        "vendor": _party(seller),
        "buyer": _party(buyer),
        "place_of_supply": buyer.state,
        "currency": "INR",
        "line_items": [
            {
                "description": d,
                "hsn_sac": h,
                "quantity": float(q),
                "unit_price": _money(p),
                "amount": _money(a),
            }
            for d, h, q, p, a in lines
        ],
        "subtotal": _money(subtotal),
        "taxes": [{"type": k, "rate_percent": float(r), "amount": _money(a)} for k, r, a in taxes],
        "total": _money(total),
    }
    return bytes(pdf.output()), truth


def receipt(seed: int) -> tuple[bytes, dict[str, Any]]:
    rng = random.Random(seed)
    merchant = rng.choice(MERCHANTS)
    iso, _printed = _date(rng)
    time = f"{rng.randint(8, 21):02d}:{rng.randint(0, 59):02d}"
    number = str(rng.randint(10000, 99999))
    rows = [(name, rng.randint(1, 3), price) for name, price in rng.sample(FOOD, rng.randint(2, 4))]
    subtotal = sum((price * qty for _, qty, price in rows), Decimal(0))
    tax = (subtotal * Decimal("0.05")).quantize(TWO)
    method = rng.choice(["UPI", "Cash", "Card"])

    pdf = _Doc()
    pdf.text_line(merchant.name, bold=True, size=14)
    pdf.text_line(f"{merchant.line1}, {merchant.city}, {merchant.state} {merchant.pin}")
    pdf.text_line(f"GSTIN: {merchant.gstin}")
    pdf.text_line(f"Bill No: {number}      Date: {iso[8:]}/{iso[5:7]}/{iso[:4]}      Time: {time}")
    pdf.ln(2)
    pdf.grid(
        ["Item", "Qty", "Amount"], [[n, str(q), f"{p * q:,.2f}"] for n, q, p in rows], [90, 20, 40]
    )
    pdf.ln(2)
    pdf.text_line(f"Subtotal: {subtotal:,.2f}")
    pdf.text_line(f"GST 5%: {tax:,.2f}")
    pdf.text_line(f"TOTAL PAID: INR {subtotal + tax:,.2f}   ({method})", bold=True)
    pdf.text_line("Synthetic receipt generated for DocFlow evals.", size=8)

    truth = {
        "receipt_number": number,
        "date": iso,
        "time": time,
        "merchant": _party(merchant),
        "currency": "INR",
        "line_items": [
            {"description": n, "quantity": float(q), "amount": _money(p * q)} for n, q, p in rows
        ],
        "subtotal": _money(subtotal),
        "tax_total": _money(tax),
        "total": _money(subtotal + tax),
        "payment_method": method,
    }
    return bytes(pdf.output()), truth


def purchase_order(seed: int) -> tuple[bytes, dict[str, Any]]:
    rng = random.Random(seed)
    buyer, vendor = rng.choice(BUYERS), rng.choice(SELLERS)
    iso, printed = _date(rng)
    delivery_iso = f"{iso[:8]}{min(int(iso[8:]) + 7, 28):02d}"
    number = f"PO-{rng.randint(1000, 9999)}"
    lines = _lines(rng)
    subtotal = sum((line[4] for line in lines), Decimal(0))
    taxes = _tax_lines(subtotal, buyer.state_code == vendor.state_code, Decimal(18))
    total = subtotal + sum((t[2] for t in taxes), Decimal(0))

    pdf = _Doc()
    pdf.text_line("PURCHASE ORDER", bold=True, size=16)
    pdf.text_line(f"PO Number: {number}      PO Date: {printed}")
    pdf.text_line(f"Deliver by: {delivery_iso[8:]}-{delivery_iso[5:7]}-{delivery_iso[:4]}")
    pdf.ln(2)
    pdf.text_line(f"Buyer: {buyer.name}", bold=True)
    pdf.text_line(f"{buyer.line1}, {buyer.city}, {buyer.state} {buyer.pin}   GSTIN: {buyer.gstin}")
    pdf.text_line(f"Supplier: {vendor.name}", bold=True)
    pdf.text_line(
        f"{vendor.line1}, {vendor.city}, {vendor.state} {vendor.pin}   GSTIN: {vendor.gstin}"
    )
    pdf.ln(3)
    pdf.grid(
        ["Description", "HSN/SAC", "Qty", "Rate (INR)", "Amount (INR)"],
        [[d, h, str(q), f"{p:,.2f}", f"{a:,.2f}"] for d, h, q, p, a in lines],
        [70, 25, 15, 35, 40],
    )
    pdf.ln(2)
    pdf.text_line(f"Subtotal: INR {subtotal:,.2f}")
    for kind, rate, amount in taxes:
        pdf.text_line(f"{kind} @ {rate.normalize()}%: INR {amount:,.2f}")
    pdf.text_line(f"Order Total: INR {total:,.2f}", bold=True)
    pdf.text_line("Synthetic purchase order generated for DocFlow evals.", size=8)

    truth = {
        "po_number": number,
        "po_date": iso,
        "delivery_date": delivery_iso,
        "buyer": _party(buyer),
        "vendor": _party(vendor),
        "currency": "INR",
        "line_items": [
            {
                "description": d,
                "hsn_sac": h,
                "quantity": float(q),
                "unit_price": _money(p),
                "amount": _money(a),
            }
            for d, h, q, p, a in lines
        ],
        "subtotal": _money(subtotal),
        "taxes": [{"type": k, "rate_percent": float(r), "amount": _money(a)} for k, r, a in taxes],
        "total": _money(total),
    }
    return bytes(pdf.output()), truth


def as_photo(pdf_bytes: bytes, seed: int) -> bytes:
    """The first page as a slightly rotated, noisy, soft JPEG, like a phone photo."""
    rng = random.Random(seed)
    document = pdfium.PdfDocument(pdf_bytes)
    try:
        page = document[0]
        image = page.render(scale=110 / 72).to_pil().convert("RGB")
        page.close()
    finally:
        document.close()
    image = image.rotate(rng.uniform(-2.5, 2.5), expand=True, fillcolor=(236, 233, 226))
    noise = Image.effect_noise(image.size, 28).convert("RGB")
    image = Image.blend(image, noise, 0.08).filter(ImageFilter.GaussianBlur(0.6))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=72, optimize=True)
    return buffer.getvalue()
