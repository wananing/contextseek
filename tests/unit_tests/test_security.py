"""Tests for security policy."""

from contextseek.config.strategies import WriteStrategy
from contextseek.security.policy import (
    apply_write_policy,
    can_access_payload,
    redact_value,
    source_allowed,
)


class TestSourceAllowed:
    def test_allow_any(self):
        strategy = WriteStrategy(allow_any_source=True)
        assert source_allowed({"source": "anything"}, strategy=strategy) is True

    def test_restrict(self):
        strategy = WriteStrategy(allow_any_source=False, allowed_sources=("cli",))
        assert source_allowed({"source": "cli"}, strategy=strategy) is True
        assert source_allowed({"source": "other"}, strategy=strategy) is False


class TestRedaction:
    def test_redact_email(self):
        strategy = WriteStrategy(redact_sensitive=True)
        result = redact_value("contact: user@example.com", strategy=strategy)
        assert "user@example.com" not in result
        assert "[REDACTED]" in result

    def test_no_redaction(self):
        strategy = WriteStrategy(redact_sensitive=False)
        result = redact_value("user@example.com", strategy=strategy)
        assert result == "user@example.com"


class TestAccessControl:
    def test_scope_mismatch(self):
        strategy = WriteStrategy(acl_enabled=True)
        payload = {"scope": "acme/proj/user1"}
        assert (
            can_access_payload(payload, scope="acme/proj/user2", strategy=strategy)
            is False
        )

    def test_scope_match(self):
        strategy = WriteStrategy(acl_enabled=True)
        payload = {"scope": "acme/proj/user1"}
        assert (
            can_access_payload(payload, scope="acme/proj/user1", strategy=strategy)
            is True
        )

    def test_acl_disabled(self):
        strategy = WriteStrategy(acl_enabled=False)
        payload = {"scope": "acme/proj/user1"}
        assert (
            can_access_payload(payload, scope="acme/proj/user1", strategy=strategy)
            is True
        )


class TestApplyWritePolicy:
    def test_drop_fields(self):
        strategy = WriteStrategy(drop_fields=("secret",))
        result = apply_write_policy(
            {"name": "ok", "secret": "hidden"}, strategy=strategy
        )
        assert "secret" not in result
        assert result["name"] == "ok"
