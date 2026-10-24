import pytest

from app.identity.models import WORKSPACE_NAME_MAX_LENGTH
from app.identity.service import default_workspace_name


@pytest.mark.parametrize(
    ("display_name", "email", "expected"),
    [
        ("Ada Lovelace", "ada@example.com", "Ada Lovelace's workspace"),
        (None, "ada.l@example.com", "ada.l's workspace"),
        ("   ", "ada@example.com", "ada's workspace"),
        (None, None, "My workspace"),
        (None, "@example.com", "My workspace"),
        ("Zoë Ångström", None, "Zoë Ångström's workspace"),
    ],
)
def test_ac8_default_name_prefers_display_name_then_email_then_fallback(
    display_name: str | None, email: str | None, expected: str
) -> None:
    assert default_workspace_name(display_name=display_name, email=email) == expected


@pytest.mark.parametrize("name", ["x" * 200, "名" * 100, "🙂" * 90])
def test_ac8_long_names_are_cut_to_the_limit_without_splitting_characters(name: str) -> None:
    result = default_workspace_name(display_name=name, email=None)

    assert len(result) <= WORKSPACE_NAME_MAX_LENGTH  # Postgres char_length counts code points
    assert result == result.strip()
    assert name.startswith(result[:10])
    result.encode("utf-8")  # still valid text: no half characters
