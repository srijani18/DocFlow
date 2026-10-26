"""CORD v2 receipts (CC BY 4.0, Hugging Face naver-clova-ix/cord-v2) mapped to receipt.v1.

CORD labels menu lines, subtotal, tax and total; everything else is masked as unlabelled
(F11 plan §4). Prices are Indonesian rupiah with "." or "," as thousands separators.
"""

import io
import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from PIL import Image

ROWS_URL = "https://datasets-server.huggingface.co/rows"
LICENCE = "CC BY 4.0 (CORD v2, NAVER CLOVA, https://huggingface.co/datasets/naver-clova-ix/cord-v2)"
UNLABELLED = [
    "receipt_number",
    "date",
    "time",
    "merchant",
    "merchant.*",
    "currency",
    "payment_method",
    "line_items.*.amount.currency",
    "subtotal.currency",
    "tax_total.currency",
    "total.currency",
]
MAX_SIDE = 1600


def parse_amount(raw: object) -> Decimal | None:
    """ "60.000" / "60,000" / "Rp 60.000,-" → 60000. Rupiah has no cents in CORD."""
    if raw is None:
        return None
    text = str(raw).strip()
    digits = re.sub(r"[^0-9]", "", text)
    if not digits:
        return None
    try:
        amount = Decimal(digits)
    except InvalidOperation:
        return None
    return -amount if text.startswith("-") else amount  # discounts are written "-60.000"


def _money(raw: object) -> dict[str, Any] | None:
    amount = parse_amount(raw)
    return None if amount is None else {"amount": float(amount), "currency": "IDR"}


def _item(name: object, count: object, price: object) -> dict[str, Any]:
    quantity = parse_amount(re.sub(r"[^0-9]", "", str(count or "")) or None)
    return {
        "description": str(name or "").strip() or None,
        "quantity": None if quantity is None else float(quantity),
        "amount": _money(price),
    }


def map_ground_truth(gt_parse: dict[str, Any]) -> dict[str, Any]:
    menu = gt_parse.get("menu") or []
    if isinstance(menu, dict):
        menu = [menu]
    items = []
    for line in menu:
        items.append(_item(line.get("nm"), line.get("cnt"), line.get("price")))
        # Add-ons ("+ coconut jelly") are labelled under the line they belong to, but are
        # printed as lines of their own with their own price.
        subs = line.get("sub") or []
        for sub in [subs] if isinstance(subs, dict) else subs:
            items.append(_item(sub.get("nm"), sub.get("cnt"), sub.get("price")))
    sub_total = gt_parse.get("sub_total") or {}
    total = gt_parse.get("total") or {}
    return {
        "receipt_number": None,
        "date": None,
        "time": None,
        "merchant": None,
        "currency": "IDR",
        "line_items": items,
        "subtotal": _money(sub_total.get("subtotal_price")),
        "tax_total": _money(sub_total.get("tax_price")),
        "total": _money(total.get("total_price")),
        "payment_method": None,
    }


def unlabelled_for(truth: dict[str, Any]) -> list[str]:
    """CORD leaves some amounts unlabelled even when they're printed (e.g. no total_price on
    a receipt that shows a total). A missing label means "unknown", not "not on the
    document", so those paths are masked rather than expected to be null."""
    extra = [name for name in ("subtotal", "tax_total", "total") if truth[name] is None]
    return UNLABELLED + extra + [f"{name}.*" for name in extra]


def fetch(count: int, http: httpx.Client) -> list[tuple[bytes, dict[str, Any]]]:
    """The first `count` test receipts as (JPEG bytes, mapped truth)."""
    response = http.get(
        ROWS_URL,
        params={
            "dataset": "naver-clova-ix/cord-v2",
            "config": "default",
            "split": "test",
            "offset": 0,
            "length": count,
        },
        timeout=60,
    )
    response.raise_for_status()
    receipts = []
    for row in response.json()["rows"]:
        image_bytes = http.get(row["row"]["image"]["src"], timeout=60).content
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        image.thumbnail((MAX_SIDE, MAX_SIDE))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=80, optimize=True)
        truth = map_ground_truth(json.loads(row["row"]["ground_truth"])["gt_parse"])
        receipts.append((buffer.getvalue(), truth))
    return receipts
