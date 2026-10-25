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


def test_llm_token_counts_are_not_redacted() -> None:
    event = {"input_tokens": 744, "output_tokens": 20, "access_token": "eyJ...", "id_token": "x"}

    result = redact_sensitive(None, "info", event)

    assert (result["input_tokens"], result["output_tokens"]) == (744, 20)
    assert result["access_token"] == REDACTED
    assert result["id_token"] == REDACTED
