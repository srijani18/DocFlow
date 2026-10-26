"""Application settings, read from environment variables.

Locally, values also come from the repo-root `.env` (copied from `.env.example`).
Every field here must be documented in `.env.example`; a test enforces it.
"""

from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal, overload

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


class DatabaseSettings(BaseSettings):
    """Just what Alembic needs. Migrations run before the app starts (start.sh) and in CI
    without a .env file, so they must not require settings they don't use."""

    model_config = SettingsConfigDict(env_file=REPO_ROOT_ENV_FILE, extra="ignore", frozen=True)

    # Supabase shared pooler, session mode (ADR-0007). Used by the app and by Alembic.
    database_url: str

    @field_validator("database_url")
    @classmethod
    def _use_psycopg_driver(cls, value: str) -> str:
        # Supabase and Docker hand out `postgres://` / `postgresql://` URLs; SQLAlchemy
        # needs the driver named explicitly.
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value.removeprefix(prefix)
        return value


class Settings(DatabaseSettings):
    role: Role = Role.ALL
    environment: Literal["local", "test", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    port: int = 8000

    # Supabase project URL, e.g. https://<ref>.supabase.co. Token issuer and JWKS derive from it.
    supabase_url: str
    auth_jwt_audience: str = "authenticated"
    auth_jwks_cache_ttl_seconds: float = 600

    # Supabase Storage (ADR-0004). Without a secret key, storage endpoints answer 503.
    supabase_secret_key: str | None = None
    supabase_storage_bucket: str = "documents-dev"

    # Encrypts workspaces' own AI keys (F15, ADR-0008): "v1:<base64 32 bytes>[,v2:…]".
    # Without it, keys can't be saved and documents fail with no_ai_key.
    byok_master_keys: str | None = None

    # LLM gateway (F4, F5). Model IDs and prompt versions are configuration (constitution §5.7).
    # Provider keys are not settings: each workspace brings its own (F15).
    gemini_base_url: str = "https://generativelanguage.googleapis.com"
    llm_timeout_seconds: float = 60
    llm_classify_model: str = "gemini-flash-lite-latest"
    llm_classify_prompt: str = "classify/v1"
    # Flash-Lite, not Flash: on the free tier Flash timed out or returned 503 while Flash-Lite
    # extracted the synthetic invoice correctly in about 6 s (F5 spec D1, measured 2026-10-26).
    llm_extract_model: str = "gemini-flash-lite-latest"
    llm_extract_prompt: str = "extract/v1"

    cors_allowed_origins: Annotated[list[str], NoDecode] = []
    cors_allowed_origin_regex: str | None = None

    @field_validator("supabase_url")
    @classmethod
    def _http_url_without_trailing_slash(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("https://", "http://")):
            raise ValueError("must be an http(s) URL, e.g. https://<ref>.supabase.co")
        return value

    @property
    def auth_issuer(self) -> str:
        """The `iss` claim Supabase puts in access tokens."""
        return f"{self.supabase_url}/auth/v1"

    @property
    def auth_jwks_url(self) -> str:
        return f"{self.auth_issuer}/.well-known/jwks.json"

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_commas(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@overload
def load_settings(env_file: Path | None = REPO_ROOT_ENV_FILE) -> Settings: ...


@overload
def load_settings[S: DatabaseSettings](
    env_file: Path | None = REPO_ROOT_ENV_FILE, *, settings_class: type[S]
) -> S: ...


def load_settings(
    env_file: Path | None = REPO_ROOT_ENV_FILE,
    *,
    settings_class: type[DatabaseSettings] = Settings,
) -> DatabaseSettings:
    """Load settings or fail fast, naming the bad variables but never their values."""
    try:
        return settings_class(_env_file=env_file)
    except ValidationError as exc:
        names = sorted({str(error["loc"][0]).upper() for error in exc.errors() if error["loc"]})
        raise ConfigError("Missing or invalid environment variables: " + ", ".join(names)) from None
