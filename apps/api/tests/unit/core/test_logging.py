from app.core.logging import REDACTED, redact_sensitive


def test_redaction_processor_masks_sensitive_keys() -> None:
    event = {
        "event": "login",
        "user_id": "u-1",
        "email": "a@example.com",
        "Authorization": "Bearer abc",
        "headers": {"cookie": "sb=1", "accept": "json"},
        "supabase_secret_key": "sb_secret_x",
        "items": [{"refresh_token": "r"}],
    }

    result = redact_sensitive(None, "info", event)

    assert result["event"] == "login"
    assert result["user_id"] == "u-1"
    assert result["email"] == REDACTED
    assert result["Authorization"] == REDACTED
    assert result["headers"] == {"cookie": REDACTED, "accept": "json"}
    assert result["supabase_secret_key"] == REDACTED
    assert result["items"] == [{"refresh_token": REDACTED}]
