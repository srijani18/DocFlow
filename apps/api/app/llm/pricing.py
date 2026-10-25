"""Estimated cost per call from a versioned price table (F4 spec D3).

Free-tier spend is $0; the estimate makes "cost per document" meaningful anyway. Prices are
list prices per million tokens, keyed by the concrete model the provider reports.
"""

import json
from decimal import Decimal
from functools import cache
from pathlib import Path

PRICES_FILE = Path(__file__).parent / "prices.v1.json"
MILLION = Decimal(1_000_000)


@cache
def _prices() -> dict[str, dict[str, dict[str, Decimal]]]:
    raw = json.loads(PRICES_FILE.read_text(), parse_float=Decimal)
    return {
        provider: {model: dict(rates) for model, rates in models.items()}
        for provider, models in raw["providers"].items()
    }


def estimate_cost(
    provider: str, model: str, *, input_tokens: int | None, output_tokens: int | None
) -> Decimal | None:
    """USD, or None when the model isn't in the table: never a guess (F4 plan §3)."""
    rates = _prices().get(provider, {}).get(model)
    if rates is None or input_tokens is None or output_tokens is None:
        return None
    cost = (
        Decimal(input_tokens) * rates["input_per_mtok"]
        + Decimal(output_tokens) * rates["output_per_mtok"]
    ) / MILLION
    return cost.quantize(Decimal("0.000001"))
