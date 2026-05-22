"""Tests for ContextSeek.delete (hard remove)."""

import pytest

from contextseek.client.contextseek import ContextSeek


def test_delete_removes_payload() -> None:
    ctx = ContextSeek()
    item = ctx.add("hello", scope="s/a/b", source="t")
    ref = ctx.resolver.ref_for("s/a/b", item.id)
    assert ctx.adapter.read(ref) is not None
    ctx.delete(ref, scope="s/a/b", reason="test")
    assert ctx.adapter.read(ref) is None


def test_delete_missing_raises() -> None:
    ctx = ContextSeek()
    ref = ctx.resolver.ref_for("s/a/b", "nonexistent-id")
    with pytest.raises(ValueError, match="not found"):
        ctx.delete(ref, scope="s/a/b", reason="x")


def test_forget_then_delete_purges_tombstone() -> None:
    ctx = ContextSeek()
    item = ctx.add("hello", scope="s/a/b", source="t")
    ref = ctx.resolver.ref_for("s/a/b", item.id)
    ctx.forget(ref, scope="s/a/b", reason="soft")
    assert ctx.adapter.read(ref) is not None
    ctx.delete(ref, scope="s/a/b", reason="purge")
    assert ctx.adapter.read(ref) is None
