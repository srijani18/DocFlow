import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from app import schemas_registry
from app.extractions import envelope
from app.llm.gateway import Gateway
from app.llm.types import InvalidOutputError, ProviderResponse

SAMPLES = Path(__file__).resolve().parents[5] / "evals" / "samples"
DOCUMENT_SCHEMAS = ["docflow/invoice/v1", "docflow/receipt/v1", "docflow/purchase_order/v1"]


def truth(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((SAMPLES / f"{name}.json").read_text())
    return loaded


def test_ac2_schemas_valid_draft_2020_12() -> None:
    files = sorted(schemas_registry.SCHEMAS_DIR.rglob("*.json"))
    assert len(files) >= 8
    for path in files:
        Draft202012Validator.check_schema(json.loads(path.read_text()))


@pytest.mark.parametrize("sample", ["synthetic-invoice-001", "synthetic-receipt-001"])
def test_ac2_examples_validate(sample: str) -> None:
    expected = truth(sample)

    assert schemas_registry.validation_errors(expected["schema_id"], expected["data"]) == []


@pytest.mark.parametrize(
    "gstin", ["29ABCDE1234F1Z", "29abcde1234f1z5", "29ABCDE1234F0Z5", "AB29CDE1234F1Z5"]
)
def test_ac2_bad_gstin_rejected(gstin: str) -> None:
    data = truth("synthetic-invoice-001")["data"]
    data["vendor"]["gstin"] = gstin

    [problem] = schemas_registry.validation_errors("docflow/invoice/v1", data)
    assert problem.startswith(f"vendor.gstin: {gstin!r} does not match")


def _allows_null(schema: dict[str, Any]) -> bool:
    types = schema.get("type")
    if types == "null" or (isinstance(types, list) and "null" in types):
        return True
    return any(_allows_null(option) for option in schema.get("anyOf", []))


def _walk(schema: dict[str, Any], path: str, problems: list[str]) -> None:
    for option in schema.get("anyOf", []):
        _walk(option, path, problems)
    if "properties" in schema:
        if schema.get("additionalProperties") is not False:
            problems.append(f"{path}: additionalProperties must be false")
        if sorted(schema.get("required", [])) != sorted(schema["properties"]):
            problems.append(f"{path}: every property must be required")
        for name, sub in schema["properties"].items():
            if sub.get("type") != "array" and not _allows_null(sub):
                problems.append(f"{path}.{name}: must allow null")
            _walk(sub, f"{path}.{name}", problems)
    if "items" in schema:
        _walk(schema["items"], f"{path}[]", problems)


@pytest.mark.parametrize("schema_id", DOCUMENT_SCHEMAS)
def test_ac2_every_property_required_and_nullable(schema_id: str) -> None:
    problems: list[str] = []
    _walk(schemas_registry.bundle(schema_id), schema_id, problems)

    assert problems == []


def test_missing_and_extra_fields_rejected() -> None:
    data = truth("synthetic-invoice-001")["data"]
    del data["due_date"]
    data["notes"] = "extra"

    problems = schemas_registry.validation_errors("docflow/invoice/v1", data)

    assert any("'due_date' is a required property" in p for p in problems)
    assert any("Additional properties are not allowed" in p for p in problems)


def answer(data: dict[str, Any], *confidence: tuple[str, float]) -> dict[str, Any]:
    return {"data": data, "confidence": [{"field": f, "score": s} for f, s in confidence]}


def test_envelope_accepts_valid_answer_and_maps_confidence() -> None:
    data = truth("synthetic-invoice-001")["data"]
    good = answer(data, ("vendor.gstin", 0.98), ("line_items.2.amount.amount", 0.7))

    assert envelope.validate("docflow/invoice/v1", good) == []
    assert envelope.confidence_map(good) == {
        "vendor.gstin": Decimal("0.98"),
        "line_items.2.amount.amount": Decimal("0.7"),
    }


@pytest.mark.parametrize("field", ["vendor.phone", "line_items.9.amount", "total.amount.value", ""])
def test_ac3_unknown_confidence_path_invalid(field: str) -> None:
    data = truth("synthetic-invoice-001")["data"]

    problems = envelope.validate("docflow/invoice/v1", answer(data, (field, 0.9)))

    assert problems == [f"confidence: {field!r} is not a field in data"]


@pytest.mark.parametrize("score", [-0.1, 1.01])
def test_ac3_confidence_out_of_range_invalid(score: float) -> None:
    data = truth("synthetic-invoice-001")["data"]

    problems = envelope.validate("docflow/invoice/v1", answer(data, ("total", score)))

    assert len(problems) == 1
    assert problems[0].startswith("confidence.0.score")


def test_ac3_invalid_data_reported_under_data() -> None:
    data = truth("synthetic-invoice-001")["data"]
    data["invoice_date"] = "14/08/2026"

    assert envelope.validate("docflow/invoice/v1", answer(data)) == [
        "data.invoice_date: '14/08/2026' is not a 'date'"
    ]


def test_ac8_amounts_parsed_as_decimal() -> None:
    text = json.dumps({"doc_type": "invoice", "confidence": 0.1}).replace(
        "0.1", "0.10000000000000000001"
    )
    parsed = Gateway._parse_and_validate(  # the parsing rule itself is the unit
        ProviderResponse(text=text, model="m", input_tokens=None, output_tokens=None),
        "docflow/classification/v1",
    )

    assert parsed["confidence"] == Decimal("0.10000000000000000001")
    with pytest.raises(InvalidOutputError):
        Gateway._parse_and_validate(
            ProviderResponse(text="{", model="m", input_tokens=None, output_tokens=None), "x"
        )


def test_response_schema_embeds_the_document_schema() -> None:
    schema = envelope.response_schema("docflow/receipt/v1")

    assert schema["properties"]["data"]["required"][0] == "receipt_number"
    assert "$ref" not in json.dumps(schema)
