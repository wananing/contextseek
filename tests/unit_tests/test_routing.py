"""Tests for scope routing/resolver."""

from contextseek.routing.resolver import ScopeResolver


class TestScopeResolver:
    def test_prefix_for(self):
        resolver = ScopeResolver()
        prefix = resolver.prefix_for("acme/proj/user1")
        assert "acme/proj/user1" in prefix

    def test_ref_for(self):
        resolver = ScopeResolver()
        ref = resolver.ref_for("acme/proj/user1", "item-123")
        assert "acme/proj/user1" in ref
        assert "item-123" in ref

    def test_parse_ref(self):
        resolver = ScopeResolver()
        ref = resolver.ref_for("acme/proj/user1", "item-123")
        scope, item_id = resolver.parse_ref(ref)
        assert scope == "acme/proj/user1"
        assert item_id == "item-123"
