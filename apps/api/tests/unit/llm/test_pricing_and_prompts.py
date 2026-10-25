from decimal import Decimal

import pytest

from app.llm.pricing import estimate_cost
from app.llm.prompts import load_prompt


def test_cost_estimate_from_price_table() -> None:
    cost = estimate_cost(
        "gemini", "gemini-3.1-flash-lite-preview", input_tokens=2_000, output_tokens=100
    )

    # 2000 tokens at $0.25/M plus 100 at $1.50/M
    assert cost == Decimal("0.000650")


def test_unknown_model_cost_is_null() -> None:
    assert estimate_cost("gemini", "gemini-9-ultra", input_tokens=10, output_tokens=10) is None
    assert (
        estimate_cost("gemini", "gemini-3-flash-preview", input_tokens=None, output_tokens=1)
        is None
    )


def test_ac6_prompt_loaded_by_version() -> None:
    prompt = load_prompt("classify/v1")

    assert (prompt.task, prompt.version) == ("classify", "classify/v1")
    assert "purchase_order" in prompt.text


@pytest.mark.parametrize(
    "version", ["classify", "classify/1", "classify/v999", "../etc/v1", "classify/v1/../../x"]
)
def test_unknown_prompt_versions_raise(version: str) -> None:
    with pytest.raises(ValueError, match="prompt"):
        load_prompt(version)
