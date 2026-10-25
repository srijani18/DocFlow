"""Ground truth of the synthetic samples in evals/samples (F5 spec D4)."""

import copy
import json
from pathlib import Path
from typing import Any

SAMPLES = Path(__file__).resolve().parents[4] / "evals" / "samples"


def sample_truth(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((SAMPLES / f"{name}.json").read_text())
    return loaded


def purchase_order_data() -> dict[str, Any]:
    """A valid purchase_order/v1 instance, derived from the synthetic invoice."""
    invoice = copy.deepcopy(sample_truth("synthetic-invoice-001")["data"])
    return {
        "po_number": "PO-SYN-7781",
        "po_date": "2026-08-01",
        "delivery_date": "2026-08-20",
        "buyer": invoice["buyer"],
        "vendor": invoice["vendor"],
        "currency": "INR",
        "line_items": invoice["line_items"],
        "subtotal": invoice["subtotal"],
        "taxes": invoice["taxes"],
        "total": invoice["total"],
    }


def envelope(data: dict[str, Any], **scores: float) -> dict[str, Any]:
    """A model answer: data plus confidence entries (dots written as __ in keywords)."""
    return {
        "data": data,
        "confidence": [{"field": f.replace("__", "."), "score": s} for f, s in scores.items()],
    }
