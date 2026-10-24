"""Export the OpenAPI document without running a server: `python -m app.openapi`.

The committed `apps/api/openapi.json` is the contract the web client is generated from
(constitution §8.6). CI regenerates it and fails on any diff.
"""

import json
import sys
from pathlib import Path

from app.core.config import Settings
from app.main import create_app

DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "openapi.json"

# Building the app never connects to the database, so a placeholder URL is enough.
_EXPORT_SETTINGS = Settings.model_validate(
    {"role": "api", "environment": "test", "database_url": "postgresql://unused@localhost/unused"}
)


def export_openapi(output: Path = DEFAULT_OUTPUT) -> None:
    document = create_app(_EXPORT_SETTINGS).openapi()
    output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    export_openapi(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT)
