"""Versioned prompt files: app/llm/prompts/<task>/v<N>.md (constitution §5.3)."""

import re
from functools import cache
from pathlib import Path

from app.llm.types import Prompt

PROMPTS_DIR = Path(__file__).parent / "prompts"
_VERSION = re.compile(r"^([a-z_]+)/(v[0-9]+)$")


@cache
def load_prompt(version: str) -> Prompt:
    """`version` is "<task>/v<N>", e.g. "classify/v1". Unknown versions raise."""
    match = _VERSION.match(version)
    if match is None:
        raise ValueError(f"prompt version must look like 'classify/v1', got {version!r}")
    task, number = match.groups()
    path = PROMPTS_DIR / task / f"{number}.md"
    if not path.is_file():
        raise ValueError(f"no prompt file for {version!r}")
    return Prompt(task=task, version=version, text=path.read_text().strip())
