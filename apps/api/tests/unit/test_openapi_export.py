import json
from pathlib import Path

from app.openapi import export_openapi


def test_openapi_export_is_deterministic_and_lists_routes(tmp_path: Path) -> None:
    first, second = tmp_path / "a.json", tmp_path / "b.json"

    export_openapi(first)
    export_openapi(second)

    assert first.read_bytes() == second.read_bytes()
    document = json.loads(first.read_text())
    assert {"/healthz", "/readyz"} <= set(document["paths"])
    assert first.read_text().endswith("\n")
    assert document["paths"]["/healthz"]["get"]["operationId"] == "healthz"
