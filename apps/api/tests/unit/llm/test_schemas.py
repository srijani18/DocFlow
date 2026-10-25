from app import schemas_registry
from app.llm.providers.gemini_schema import adapt_schema


def test_classification_schema_bundles_and_validates() -> None:
    bundled = schemas_registry.bundle("docflow/classification/v1")

    assert "$id" not in bundled
    assert bundled["required"] == ["doc_type", "confidence"]
    assert (
        schemas_registry.validation_errors(
            "docflow/classification/v1", {"doc_type": "invoice", "confidence": 0.9}
        )
        == []
    )
    assert schemas_registry.validation_errors(
        "docflow/classification/v1", {"doc_type": "letter", "confidence": 1.5}
    ) == [
        "confidence: 1.5 is greater than the maximum of 1",
        "doc_type: 'letter' is not one of ['invoice', 'receipt', 'purchase_order', 'other']",
    ]


def test_schema_adapter_inlines_refs_and_strips_x_keys() -> None:
    schema = {
        "type": "object",
        "x-schema-id": "docflow/test/v1",
        "$comment": "dropped",
        "properties": {
            "gstin": {"type": ["string", "null"], "pattern": "^[0-9]{2}", "x-eval": "exact"},
            # A field literally named like a keyword must survive.
            "pattern": {"type": "string", "examples": ["x"]},
        },
        "required": ["gstin", "pattern"],
        "additionalProperties": False,
    }

    assert adapt_schema(schema) == {
        "type": "object",
        "properties": {"gstin": {"type": ["string", "null"]}, "pattern": {"type": "string"}},
        "required": ["gstin", "pattern"],
        "additionalProperties": False,
    }


def test_every_schema_file_has_an_id_and_short_id() -> None:
    assert "docflow/classification/v1" in schemas_registry.schema_ids()
