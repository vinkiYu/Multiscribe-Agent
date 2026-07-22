"""Security-boundary tests for redaction."""

from multiscribe_agent.plugins.security import REDACTED, redact_data, redact_text


def test_redaction_removes_sensitive_keys_and_inline_credentials() -> None:
    payload = {
        "api_key": "sk-secret",
        "nested": {"password": "pw", "safe": "visible"},
        "message": "Authorization: Bearer abcdefghijklmnop token=private-value",
    }
    redacted = redact_data(payload)
    assert isinstance(redacted, dict)
    assert redacted["api_key"] == REDACTED
    assert redacted["nested"] == {"password": REDACTED, "safe": "visible"}
    assert "abcdefghijklmnop" not in str(redacted["message"])
    assert "private-value" not in str(redacted["message"])


def test_redact_text_leaves_normal_content_unchanged() -> None:
    assert redact_text("ordinary tool result") == "ordinary tool result"
