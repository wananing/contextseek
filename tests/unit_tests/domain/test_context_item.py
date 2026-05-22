"""Tests for ContextItem domain model."""

from datetime import datetime, timezone

from contextseek.domain.context_item import ContextItem, _generate_id, _utc_now
from contextseek.domain.links import Link, LinkType
from contextseek.domain.provenance import Provenance, SourceType
from contextseek.domain.stages import Stage, Stability, STAGE_DEFAULT_STABILITY


def _make_item(**kwargs):
    defaults = {
        "id": _generate_id(),
        "content": "test content",
        "scope": "acme/proj/user1",
        "provenance": Provenance(
            source_type=SourceType.human_input,
            source_id="test",
            confidence=1.0,
        ),
        "stage": Stage.knowledge,
        "tags": ["test"],
        "links": [],
        "created_at": _utc_now(),
    }
    defaults.update(kwargs)
    return ContextItem(**defaults)


class TestContextItem:
    def test_create_basic(self):
        item = _make_item()
        assert item.stage == Stage.knowledge
        assert item.stability == Stability.stable
        assert item.searchable is True
        assert item.is_deleted is False

    def test_content_text_string(self):
        item = _make_item(content="hello world")
        assert item.content_text == "hello world"

    def test_content_text_dict(self):
        item = _make_item(content={"key": "value", "nested": {"a": 1}})
        assert "key" in item.content_text
        assert "value" in item.content_text

    def test_auto_hash(self):
        item = _make_item(content="unique content")
        assert item.hash != ""
        item2 = _make_item(content="unique content")
        assert item.hash == item2.hash

    def test_different_content_different_hash(self):
        item1 = _make_item(content="content A")
        item2 = _make_item(content="content B")
        assert item1.hash != item2.hash

    def test_stability_auto_inferred(self):
        for stage, expected in STAGE_DEFAULT_STABILITY.items():
            item = _make_item(stage=stage)
            assert item.stability == expected

    def test_touch(self):
        item = _make_item()
        old_count = item.access_count
        item.touch()
        assert item.access_count == old_count + 1
        assert item.last_accessed_at is not None

    def test_soft_delete(self):
        item = _make_item()
        assert item.is_deleted is False
        item.soft_delete("test reason")
        assert item.is_deleted is True
        assert item.deleted_reason == "test reason"
        assert item.searchable is False

    def test_links(self):
        item = _make_item(links=[
            Link(target_id="other-id", relation=LinkType.derived_from),
        ])
        assert len(item.links) == 1
        assert item.links[0].relation == LinkType.derived_from
