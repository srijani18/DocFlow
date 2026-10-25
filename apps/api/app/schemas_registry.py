"""Loads the JSON Schemas in `schemas/` (the single source of truth, schemas/README.md).

- `bundle(schema_id)` returns one self-contained schema with every `$ref` inlined, which is
  what an LLM provider needs (README convention 2).
- `validate(schema_id, instance)` checks an instance against the original schema with a
  draft 2020-12 validator. This is the check that decides what may be stored (ADR-0005).
"""

import json
import os
from collections.abc import Mapping
from copy import deepcopy
from functools import cache
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag, urljoin

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012


def _default_schemas_dir() -> Path:
    # apps/api/app/schemas_registry.py -> repo root is three levels above `app`. In the
    # Docker image the schemas are copied to /schemas instead (apps/api/Dockerfile).
    parents = Path(__file__).resolve().parents
    if len(parents) > 3 and (candidate := parents[3] / "schemas").is_dir():
        return candidate
    return Path("/schemas")


SCHEMAS_DIR = Path(os.environ.get("SCHEMAS_DIR") or _default_schemas_dir())


class UnknownSchemaError(KeyError):
    pass


@cache
def _documents() -> dict[str, dict[str, Any]]:
    """Every schema file, keyed by its absolute `$id` URI."""
    documents: dict[str, dict[str, Any]] = {}
    for path in sorted(SCHEMAS_DIR.rglob("*.json")):
        document = json.loads(path.read_text())
        documents[document["$id"]] = document
    return documents


@cache
def _uri_for(schema_id: str) -> str:
    for uri, document in _documents().items():
        if document.get("x-schema-id") == schema_id:
            return uri
    raise UnknownSchemaError(schema_id)


def schema_ids() -> list[str]:
    return sorted(doc["x-schema-id"] for doc in _documents().values() if "x-schema-id" in doc)


def _resolve_pointer(document: Mapping[str, Any], fragment: str) -> Any:
    node: Any = document
    for part in filter(None, fragment.lstrip("/").split("/")):
        node = node[part.replace("~1", "/").replace("~0", "~")]
    return node


def _inline(node: Any, base_uri: str, root: Mapping[str, Any]) -> Any:
    if isinstance(node, list):
        return [_inline(item, base_uri, root) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        target_uri, fragment = urldefrag(urljoin(base_uri, node["$ref"]))
        target_root = _documents()[target_uri] if target_uri != base_uri else root
        target = _resolve_pointer(target_root, fragment)
        siblings = {key: value for key, value in node.items() if key != "$ref"}
        inlined = _inline(deepcopy(target), target_uri, target_root)
        return {**inlined, **_inline(siblings, base_uri, root)}
    return {
        key: _inline(value, base_uri, root)
        for key, value in node.items()
        if key not in {"$defs", "$id", "$schema"}
    }


@cache
def _bundled(schema_id: str) -> dict[str, Any]:
    uri = _uri_for(schema_id)
    root = _documents()[uri]
    bundled: dict[str, Any] = _inline(deepcopy(root), uri, root)
    return bundled


def bundle(schema_id: str) -> dict[str, Any]:
    """A self-contained copy of the schema (safe to modify)."""
    return deepcopy(_bundled(schema_id))


@cache
def _validator(schema_id: str) -> Draft202012Validator:
    registry: Registry[Any] = Registry().with_resources(
        (uri, Resource.from_contents(document, default_specification=DRAFT202012))
        for uri, document in _documents().items()
    )
    schema = _documents()[_uri_for(schema_id)]
    return Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())


def validation_errors(schema_id: str, instance: object) -> list[str]:
    """Readable problems, `path: message`; empty when the instance is valid."""
    errors = sorted(_validator(schema_id).iter_errors(instance), key=lambda e: list(e.path))
    return [f"{'.'.join(map(str, error.path)) or '<root>'}: {error.message}" for error in errors]
