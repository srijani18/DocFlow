"""What Gemini's structured output (`responseJsonSchema`) accepts.

The gateway drops everything else before sending. Dropping only makes the request looser;
our own validation still enforces the full schema (F4 plan §2).
"""

from typing import Any

SUPPORTED_KEYWORDS = frozenset(
    {
        "type",
        "properties",
        "required",
        "items",
        "enum",
        "anyOf",
        "description",
        "title",
        "format",
        "minimum",
        "maximum",
        "minItems",
        "maxItems",
        "additionalProperties",
    }
)
# Keywords whose values are maps of names to subschemas, not subschemas themselves.
_NAME_MAPS = frozenset({"properties"})


def adapt_schema(schema: Any) -> Any:
    if isinstance(schema, list):
        return [adapt_schema(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    adapted: dict[str, Any] = {}
    for key, value in schema.items():
        if key not in SUPPORTED_KEYWORDS:
            continue  # x-* keys, $comment, examples, pattern, minLength…
        if key in _NAME_MAPS:
            adapted[key] = {name: adapt_schema(sub) for name, sub in value.items()}
        else:
            adapted[key] = adapt_schema(value)
    return adapted
