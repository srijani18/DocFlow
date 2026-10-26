"""Turns a workspace's human-approved documents into eval data (F7 AC9, D4).

    make eval-import WORKSPACE=<workspace id>

Writes `evals/imported/<workspace id>/manifest.v2.json` and the files, in the dataset format.
Run it only on your own (demo) workspace: the files and data are other people's otherwise
(constitution §5.5). Evaluate with `make eval MANIFEST=evals/imported/<id>/manifest.v2.json`.
"""

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import SystemClock
from app.core.config import load_settings
from app.core.db import create_engine, create_sessionmaker
from app.core.tenancy import WorkspaceScope
from app.extractions.exact_json import dumps_exact
from app.models import import_all_models
from app.review import service as review
from app.storage.client import Storage
from app.storage.supabase import SupabaseStorage
from evals.paths import REPO_ROOT

EXTENSIONS = {"application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg"}
OPERATOR_ROLE = "operator"


async def export(
    session: AsyncSession, storage: Storage, workspace_id: uuid.UUID, out: Path
) -> list[dict[str, Any]]:
    scope = WorkspaceScope(workspace_id=workspace_id, user_id=uuid.UUID(int=0), role=OPERATOR_ROLE)
    files = out / "files"
    files.mkdir(parents=True, exist_ok=True)
    entries = []
    for approved in await review.approved_by_people(session, scope):
        document = approved.document
        name = f"review-{document.id}.{EXTENSIONS[document.content_type]}"
        (files / name).write_bytes(await storage.download(document.storage_path))
        entries.append(
            {
                "id": name.rsplit(".", 1)[0],
                "file": f"files/{name}",
                "content_type": document.content_type,
                "doc_type": document.doc_type,
                "schema_id": approved.schema_id,
                "source": "review",
                "licence": "Your own documents: keep them out of the public repo if private",
                "unlabelled": [],
                "expected_issues": [],
                "corrections": approved.corrections,
                "truth": json.loads(dumps_exact(approved.data)),
            }
        )
    (out / "manifest.v2.json").write_text(
        json.dumps({"version": 2, "documents": entries}, indent=2, ensure_ascii=False) + "\n"
    )
    return entries


async def main(argv: list[str]) -> int:
    import_all_models()  # the ORM needs every table to resolve foreign keys
    parser = argparse.ArgumentParser(prog="python -m evals.import_reviews")
    parser.add_argument("--workspace", required=True, help="your own workspace id")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    workspace_id = uuid.UUID(args.workspace)
    out = Path(args.out) if args.out else REPO_ROOT / "evals" / "imported" / str(workspace_id)

    settings = load_settings()
    engine = create_engine(settings)
    async with httpx.AsyncClient() as http:
        storage = SupabaseStorage(
            supabase_url=settings.supabase_url,
            secret_key=settings.supabase_secret_key,
            bucket=settings.supabase_storage_bucket,
            http=http,
            clock=SystemClock(),
        )
        async with create_sessionmaker(engine)() as session:
            entries = await export(session, storage, workspace_id, out)
    await engine.dispose()
    corrected = sum(1 for entry in entries if entry["corrections"])
    print(f"wrote {len(entries)} approved documents ({corrected} corrected) to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
