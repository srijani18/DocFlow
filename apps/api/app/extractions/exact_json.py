"""JSON text with Decimals written exactly, so JSONB stores amounts digit for digit (F5 AC8)."""

import json
import re
import uuid
from decimal import Decimal
from typing import Any


def dumps_exact(value: Any) -> str:
    # json can't emit a raw number from a custom type, so Decimals go out as uniquely
    # marked strings and the quotes around them are removed afterwards.
    marker = uuid.uuid4().hex

    def encode(obj: object) -> str:
        if isinstance(obj, Decimal):
            return f"{marker}{obj}{marker}"
        raise TypeError(f"{type(obj).__name__} is not JSON serializable")

    text = json.dumps(value, default=encode, ensure_ascii=False, separators=(",", ":"))
    return re.sub(f'"{marker}([^"]*){marker}"', r"\1", text)
