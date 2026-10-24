import re
from pathlib import Path

import pytest

from app.core.config import ConfigError, Settings, load_settings

ENV_EXAMPLE = Path(__file__).resolve().parents[5] / ".env.example"


def test_settings_missing_required_vars_fails_fast_with_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ConfigError) as exc_info:
        load_settings(env_file=None)

    assert "DATABASE_URL" in str(exc_info.value)


def test_config_error_never_echoes_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:s3cret@host/db")
    monkeypatch.setenv("PORT", "not-a-number")

    with pytest.raises(ConfigError) as exc_info:
        load_settings(env_file=None)

    assert "PORT" in str(exc_info.value)
    assert "s3cret" not in str(exc_info.value)


@pytest.mark.parametrize(
    "raw",
    [
        "postgres://u:p@host:5432/postgres?sslmode=require",
        "postgresql://u:p@host:5432/postgres?sslmode=require",
        "postgresql+psycopg://u:p@host:5432/postgres?sslmode=require",
    ],
)
def test_database_url_uses_the_psycopg_driver(raw: str) -> None:
    settings = Settings(_env_file=None, database_url=raw, supabase_url="https://abc.supabase.co")

    assert settings.database_url == "postgresql+psycopg://u:p@host:5432/postgres?sslmode=require"


def test_cors_origins_parse_from_comma_separated_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    monkeypatch.setenv("SUPABASE_URL", "https://abc.supabase.co")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000, https://docflow.vercel.app")

    settings = load_settings(env_file=None)

    assert settings.cors_allowed_origins == ["http://localhost:3000", "https://docflow.vercel.app"]


def test_env_example_lists_every_setting() -> None:
    documented = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", ENV_EXAMPLE.read_text(), re.M))

    missing = {name.upper() for name in Settings.model_fields} - documented

    assert not missing, f"Add these to .env.example: {sorted(missing)}"


@pytest.mark.parametrize(
    "raw", ["https://abc.supabase.co", "https://abc.supabase.co/", "  https://abc.supabase.co  "]
)
def test_supabase_url_is_normalised_and_drives_issuer_and_jwks(raw: str) -> None:
    settings = Settings(_env_file=None, database_url="postgresql://u:p@h/db", supabase_url=raw)

    assert settings.supabase_url == "https://abc.supabase.co"
    assert settings.auth_issuer == "https://abc.supabase.co/auth/v1"
    assert settings.auth_jwks_url == "https://abc.supabase.co/auth/v1/.well-known/jwks.json"


def test_supabase_url_must_be_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    monkeypatch.setenv("SUPABASE_URL", "abc.supabase.co")

    with pytest.raises(ConfigError, match="SUPABASE_URL"):
        load_settings(env_file=None)
