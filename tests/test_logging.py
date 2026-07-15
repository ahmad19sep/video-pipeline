from cutmachine.logging import redact


def test_secrets_are_redacted() -> None:
    message = "api_key=abc123 token:xyz password = hunter2 safe=value"
    redacted = redact(message)

    assert "abc123" not in redacted
    assert "xyz" not in redacted
    assert "hunter2" not in redacted
    assert "safe=value" in redacted
