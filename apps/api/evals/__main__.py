"""python -m evals --models gemini:gemini-flash-lite-latest,groq:… --limit 20 [--agent]

Uses the operator's own keys from the environment or the repo-root .env (F11 D0). Exits 0
with a message when no key is available for any requested model (F11 AC7).
"""

import argparse
import asyncio
import json
import os
import secrets
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.llm.providers import openai_compat
from app.llm.providers.base import Provider
from app.llm.providers.gemini import GeminiProvider
from app.llm.routing import parse_route
from evals import report
from evals.paths import MANIFEST, REPO_ROOT, REPORTS_DIR
from evals.runner import ModelRun, StaticKeys, load_manifest, run_model, select

KEY_VARIABLES = {
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def _env_keys() -> dict[str, str]:
    values = dict(os.environ)
    env_file = REPO_ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text().splitlines():
            name, sep, value = line.partition("=")
            if sep and not name.startswith("#") and name.strip() not in values:
                values[name.strip()] = value.strip()
    return {provider: values[var] for provider, var in KEY_VARIABLES.items() if values.get(var)}


def _commit() -> str:
    try:
        return subprocess.run(  # fixed argv
            ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
            cwd=REPO_ROOT,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


async def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals")
    parser.add_argument(
        "--models", default="gemini:gemini-flash-lite-latest", help="comma-separated provider:model"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="documents per model (stable sample)"
    )
    parser.add_argument(
        "--pace", type=float, default=0.0, help="seconds to wait between calls (free tiers)"
    )
    parser.add_argument(
        "--agent", action="store_true", help="also run the validation agent (before / after)"
    )
    parser.add_argument("--out", default=str(REPORTS_DIR))
    args = parser.parse_args(argv)

    routes = parse_route(args.models)
    operator_keys = _env_keys()
    runnable = [route for route in routes if route.provider in operator_keys]
    if not runnable:
        print("Skipping evals: no provider keys configured for " + ", ".join(map(str, routes)))
        return 0
    for route in routes:
        if route not in runnable:
            print(f"Skipping {route}: no {KEY_VARIABLES[route.provider]}")

    version, documents = load_manifest(MANIFEST)
    sample = select(documents, args.limit)
    commit = _commit()
    created = datetime.now(UTC)
    run_id = f"{created:%Y%m%d-%H%M}-{commit}-{secrets.token_hex(2)}"
    async with httpx.AsyncClient() as http:
        providers: dict[str, Provider] = {
            "gemini": GeminiProvider(http=http, timeout_seconds=90),
            "groq": openai_compat.groq(http, timeout_seconds=90),
            "openrouter": openai_compat.openrouter(http, timeout_seconds=90),
        }
        runs = []
        for route in runnable:
            print(f"{route}: {len(sample)} documents…", flush=True)
            runs.append(
                await run_model(
                    route,
                    sample,
                    providers=providers,
                    credentials=StaticKeys(operator_keys),
                    pace_seconds=args.pace,
                    agent=args.agent,
                )
            )
    meta = {
        "run_id": run_id,
        "commit": commit,
        "created_at": created.isoformat(timespec="seconds"),
        "dataset_version": version,
        "documents": len(sample),
        "prompt_versions": ["classify/v1", "extract/v1", *(["validate/v1"] if args.agent else [])],
        "models": [str(r) for r in runnable],
    }
    print(f"wrote {_write(Path(args.out), run_id, meta, runs)}")
    return 0


def _write(out: Path, run_id: str, meta: dict[str, object], runs: list[ModelRun]) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{run_id}.json").write_text(
        json.dumps(report.to_json(meta, runs), indent=2, default=str) + "\n"
    )
    markdown = out / f"{run_id}.md"
    markdown.write_text(report.to_markdown(meta, runs))
    return markdown


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
