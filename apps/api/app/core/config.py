"""Application settings, read from environment variables.

Locally, values also come from the repo-root `.env` (copied from `.env.example`).
Every field here must be documented in `.env.example`; a test enforces it.
"""

from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import ValidationError, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _repo_root_env_file() -> Path | None:
    # apps/api/app/core/config.py -> repo root is four levels up. Inside the Docker
    # image the tree is shallower and there is no .env file, which is fine.
    parents = Path(__file__).resolve().parents
    return parents[4] / ".env" if len(parents) > 4 else None


REPO_ROOT_ENV_FILE = _repo_root_env_file()


class Role(StrEnum):
    """Which parts of the modular monolith this process runs (ADR-0002)."""

    API = "api"
    WORKER = "worker"
    ALL = "all"

    @property
    def serves_http(self) -> bool:
        return self in (Role.API, Role.ALL)

    @property
    def runs_worker(self) -> bool:
        return self in (Role.WORKER, Role.ALL)


class ConfigError(RuntimeError):
    """Raised at startup when required configuration is missing or invalid."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT_ENV_FILE, extra="ignore", frozen=True)

    role: Role = Role.ALL
    environment: Literal["local", "test", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    port: int = 8000

    # Supabase shared pooler, session mode (ADR-0007). Used by the app and by Alembic.
    database_url: str

    cors_allowed_origins: Annotated[list[str], NoDecode] = []
    cors_allowed_origin_regex: str | None = None

    @field_validator("database_url")
    @classmethod
    def _use_psycopg_driver(cls, value: str) -> str:
        # Supabase and Docker hand out `postgres://` / `postgresql://` URLs; SQLAlchemy
        # needs the driver named explicitly.
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value.removeprefix(prefix)
        return value

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_commas(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


def load_settings(env_file: Path | None = REPO_ROOT_ENV_FILE) -> Settings:
    """Load settings or fail fast, naming the bad variables but never their values."""
    try:
        return Settings(_env_file=env_file)
    except ValidationError as exc:
        names = sorted({str(error["loc"][0]).upper() for error in exc.errors() if error["loc"]})
        raise ConfigError("Missing or invalid environment variables: " + ", ".join(names)) from None
