"""Registry of ORM model modules, so Alembic and the tenant meta-test see every table."""

import importlib

# Add each feature's models module here as it is created.
MODEL_MODULES: tuple[str, ...] = (
    "app.identity.models",
    "app.documents.models",
    "app.jobs.models",
    "app.llm.models",
    "app.extractions.models",
    "app.aikeys.models",
    "app.validation.models",
    "app.review.models",
    "app.search.models",
    "app.mcp.models",
    "app.idempotency.models",
)


def import_all_models() -> None:
    for module in MODEL_MODULES:
        importlib.import_module(module)
