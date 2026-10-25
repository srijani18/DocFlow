"""Puts extraction data back in schema order. Postgres JSONB stores object keys sorted by
length then bytes, so `invoice_number` would otherwise come after `buyer` (F5 AC6)."""

from typing import Any


def order_like_schema(value: Any, schema: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        for option in schema.get("anyOf", []):  # nullable objects: use the object branch
            if "properties" in option:
                schema = option
        properties: dict[str, Any] = schema.get("properties", {})
        ordered = {
            key: order_like_schema(value[key], properties[key])
            for key in properties
            if key in value
        }
        ordered.update({key: item for key, item in value.items() if key not in ordered})
        return ordered
    if isinstance(value, list):
        item_schema = schema.get("items", {})
        return [order_like_schema(item, item_schema) for item in value]
    return value
