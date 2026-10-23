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
        "postgres://u:p@host:5432/db?sslmode=require",
        "postgresql://u:p@host:5432/db?sslmode=require",
        "postgresql+psycopg://u:p@host:5432/db?sslmode=require",
    ],
)
def test_database_urls_use_the_psycopg_driver(raw: str) -> None:
    settings = Settings(_env_file=None, database_url=raw, database_url_direct=raw)

    expected = "postgresql+psycopg://u:p@host:5432/db?sslmode=require"
    assert settings.database_url == expected
    assert settings.database_url_direct == expected


def test_migrations_fall_back_to_pooled_url_when_no_direct_url() -> None:
    settings = Settings(_env_file=None, database_url="postgresql://u:p@h/db")

    assert settings.migrations_database_url == "postgresql+psycopg://u:p@h/db"


def test_cors_origins_parse_from_comma_separated_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000, https://docflow.vercel.app")

    settings = load_settings(env_file=None)

    assert settings.cors_allowed_origins == ["http://localhost:3000", "https://docflow.vercel.app"]


def test_env_example_lists_every_setting() -> None:
    documented = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", ENV_EXAMPLE.read_text(), re.M))

    missing = {name.upper() for name in Settings.model_fields} - documented

    assert not missing, f"Add these to .env.example: {sorted(missing)}"
