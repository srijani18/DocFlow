"""Registry of ORM model modules, so Alembic and the tenant meta-test see every table."""

import importlib

# Add each feature's models module here as it is created (F1: "app.identity.models").
MODEL_MODULES: tuple[str, ...] = ()


def import_all_models() -> None:
    for module in MODEL_MODULES:
        importlib.import_module(module)
