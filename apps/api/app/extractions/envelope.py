"""The extraction envelope (schemas/extraction-envelope.v1.json, README convention 3).

The model answers `{data, confidence: [{field, score}]}`. A list is used on the wire because
providers handle arrays of objects more reliably than free-form maps; it is stored as the
map `{"<field path>": score}` that review (F7) and evals (F11) use.
"""

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from app.schemas_registry import bundle, validation_errors

ENVELOPE_ID = "docflow/extraction-envelope/v1"
SCHEMA_BY_DOC_TYPE = {
    "invoice": "docflow/invoice/v1",
    "receipt": "docflow/receipt/v1",
    "purchase_order": "docflow/purchase_order/v1",
}


def response_schema(schema_id: str) -> dict[str, Any]:
    """The envelope with `data` replaced by the document schema, for the provider."""
    envelope = bundle(ENVELOPE_ID)
    envelope["properties"]["data"] = bundle(schema_id)
    return envelope


def _has_path(data: Any, path: str) -> bool:
    node = data
    for part in path.split("."):
        if isinstance(node, Mapping) and part in node:
            node = node[part]
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            return False
    return True


def validate(schema_id: str, answer: Mapping[str, Any]) -> list[str]:
    """Problems with an answer, empty when it may be stored (F5 AC3)."""
    problems = validation_errors(ENVELOPE_ID, answer)
    if problems:
        return problems
    problems = [f"data.{problem}" for problem in validation_errors(schema_id, answer["data"])]
    for entry in answer["confidence"]:
        if not _has_path(answer["data"], entry["field"]):
            problems.append(f"confidence: {entry['field']!r} is not a field in data")
    return problems


def confidence_map(answer: Mapping[str, Any]) -> dict[str, Decimal]:
    """`[{field, score}]` to `{field: score}`; a repeated field keeps its last score."""
    return {entry["field"]: Decimal(str(entry["score"])) for entry in answer["confidence"]}
