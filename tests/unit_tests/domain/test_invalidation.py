"""Tests for domain.invalidation — confidence degradation propagation."""

from __future__ import annotations

from contextseek.domain.context_item import ContextItem
from contextseek.domain.invalidation import (
    InvalidationResult,
    propagate_invalidation,
)
from contextseek.domain.links import Link, LinkType
from contextseek.domain.provenance import Provenance, SourceType
from contextseek.domain.stages import Stage


def _make_item(
    item_id: str,
    confidence: float = 0.8,
    links: list[Link] | None = None,
    effective_confidence: float | None = None,
) -> ContextItem:
    item = ContextItem(
        id=item_id,
        content=f"content of {item_id}",
        scope="test/scope",
        provenance=Provenance(
            source_type=SourceType.document,
            source_id=f"source_{item_id}",
            confidence=confidence,
        ),
        stage=Stage.knowledge,
        links=links or [],
    )
    if effective_confidence is not None:
        item.effective_confidence = effective_confidence
    return item


class TestSingleLayerPropagation:
    """Test invalidation affecting direct dependents."""

    def test_single_dependent_is_degraded(self):
        # parent -> child (child derived_from parent)
        parent = _make_item("parent", confidence=0.9)
        child = _make_item(
            "child",
            confidence=0.5,
            links=[Link(target_id="parent", relation=LinkType.derived_from)],
            effective_confidence=0.81,  # was computed from parent
        )

        dependents_map = {"parent": [(child, LinkType.derived_from, 1.0)]}
        items_map = {"parent": parent, "child": child}

        result = propagate_invalidation(
            parent,
            find_dependents=lambda item_id: dependents_map.get(item_id, []),
            resolve_item=lambda item_id: items_map.get(item_id),
        )

        assert len(result.degraded_items) == 1
        assert result.degraded_items[0].item_id == "child"
        assert (
            result.degraded_items[0].new_confidence
            < result.degraded_items[0].old_confidence
        )

    def test_no_dependents_means_empty_result(self):
        parent = _make_item("parent", confidence=0.9)

        result = propagate_invalidation(
            parent,
            find_dependents=lambda _: [],
            resolve_item=lambda _: None,
        )

        assert len(result.degraded_items) == 0
        assert len(result.reverification_needed) == 0
        assert result.propagation_depth == 0


class TestMultipleParents:
    """Test that items with multiple parents degrade gracefully."""

    def test_surviving_parent_mitigates_degradation(self):
        parent_a = _make_item("pa", confidence=0.9)
        parent_b = _make_item("pb", confidence=0.8)
        child = _make_item(
            "child",
            confidence=0.5,
            links=[
                Link(target_id="pa", relation=LinkType.derived_from),
                Link(target_id="pb", relation=LinkType.supported_by),
            ],
            effective_confidence=0.85,
        )

        # Delete parent_a — child still has parent_b
        dependents_map = {"pa": [(child, LinkType.derived_from, 1.0)]}
        items_map = {"pa": parent_a, "pb": parent_b, "child": child}

        result = propagate_invalidation(
            parent_a,
            find_dependents=lambda item_id: dependents_map.get(item_id, []),
            resolve_item=lambda item_id: items_map.get(item_id),
        )

        assert len(result.degraded_items) == 1
        # With surviving parent_b, confidence should still be decent
        new_conf = result.degraded_items[0].new_confidence
        assert new_conf > 0.3  # not completely destroyed

    def test_sole_parent_deletion_causes_major_degradation(self):
        parent = _make_item("parent", confidence=0.9)
        child = _make_item(
            "child",
            confidence=0.3,
            links=[Link(target_id="parent", relation=LinkType.derived_from)],
            effective_confidence=0.81,
        )

        dependents_map = {"parent": [(child, LinkType.derived_from, 1.0)]}
        items_map = {"parent": parent, "child": child}

        result = propagate_invalidation(
            parent,
            find_dependents=lambda item_id: dependents_map.get(item_id, []),
            resolve_item=lambda item_id: items_map.get(item_id),
        )

        assert len(result.degraded_items) == 1
        # No other parent → falls back to intrinsic (0.3)
        new_conf = result.degraded_items[0].new_confidence
        assert new_conf == 0.3


class TestReverificationThreshold:
    """Test that items below threshold are flagged."""

    def test_below_threshold_flagged(self):
        parent = _make_item("parent", confidence=0.9)
        child = _make_item(
            "child",
            confidence=0.2,  # low intrinsic
            links=[Link(target_id="parent", relation=LinkType.derived_from)],
            effective_confidence=0.7,
        )

        dependents_map = {"parent": [(child, LinkType.derived_from, 1.0)]}
        items_map = {"parent": parent, "child": child}

        result = propagate_invalidation(
            parent,
            find_dependents=lambda item_id: dependents_map.get(item_id, []),
            resolve_item=lambda item_id: items_map.get(item_id),
            reverification_threshold=0.4,
        )

        # Child falls to intrinsic 0.2 < threshold 0.4
        assert "child" in result.reverification_needed

    def test_above_threshold_not_flagged(self):
        parent = _make_item("parent", confidence=0.9)
        child = _make_item(
            "child",
            confidence=0.6,  # decent intrinsic
            links=[Link(target_id="parent", relation=LinkType.derived_from)],
            effective_confidence=0.8,
        )

        dependents_map = {"parent": [(child, LinkType.derived_from, 1.0)]}
        items_map = {"parent": parent, "child": child}

        result = propagate_invalidation(
            parent,
            find_dependents=lambda item_id: dependents_map.get(item_id, []),
            resolve_item=lambda item_id: items_map.get(item_id),
            reverification_threshold=0.4,
        )

        # Child falls to intrinsic 0.6 > threshold 0.4
        assert "child" not in result.reverification_needed


class TestMultiLayerPropagation:
    """Test cascading propagation through multiple layers."""

    def test_two_layer_cascade(self):
        # grandparent -> parent -> child
        grandparent = _make_item("gp", confidence=0.9)
        parent = _make_item(
            "parent",
            confidence=0.5,
            links=[Link(target_id="gp", relation=LinkType.derived_from)],
            effective_confidence=0.81,
        )
        child = _make_item(
            "child",
            confidence=0.3,
            links=[Link(target_id="parent", relation=LinkType.derived_from)],
            effective_confidence=0.65,
        )

        dependents_map = {
            "gp": [(parent, LinkType.derived_from, 1.0)],
            "parent": [(child, LinkType.derived_from, 1.0)],
        }
        items_map = {"gp": grandparent, "parent": parent, "child": child}

        result = propagate_invalidation(
            grandparent,
            find_dependents=lambda item_id: dependents_map.get(item_id, []),
            resolve_item=lambda item_id: items_map.get(item_id),
        )

        # Both parent and child should be degraded
        degraded_ids = {d.item_id for d in result.degraded_items}
        assert "parent" in degraded_ids
        # Child may or may not cascade depending on threshold
        assert result.propagation_depth >= 1


class TestDepthLimit:
    """Test max_depth prevents runaway propagation."""

    def test_propagation_respects_depth(self):
        items_map: dict[str, ContextItem] = {}
        dependents_map: dict[str, list] = {}

        # Build chain of 15 items
        for i in range(15):
            links = (
                [Link(target_id=f"item_{i - 1}", relation=LinkType.derived_from)]
                if i > 0
                else []
            )
            items_map[f"item_{i}"] = _make_item(
                f"item_{i}", confidence=0.3, links=links, effective_confidence=0.8
            )
            if i > 0:
                dependents_map.setdefault(f"item_{i - 1}", []).append(
                    (items_map[f"item_{i}"], LinkType.derived_from, 1.0)
                )

        result = propagate_invalidation(
            items_map["item_0"],
            find_dependents=lambda item_id: dependents_map.get(item_id, []),
            resolve_item=lambda item_id: items_map.get(item_id),
            max_depth=3,
        )

        # Should not propagate to all 14 dependents
        assert result.propagation_depth <= 3


class TestCycleHandling:
    """Test that cycles don't cause infinite propagation."""

    def test_mutual_dependents_terminate(self):
        item_a = _make_item(
            "a",
            confidence=0.7,
            links=[Link(target_id="b", relation=LinkType.supported_by)],
            effective_confidence=0.8,
        )
        item_b = _make_item(
            "b",
            confidence=0.7,
            links=[Link(target_id="a", relation=LinkType.supported_by)],
            effective_confidence=0.8,
        )

        # Both reference each other
        dependents_map = {
            "a": [(item_b, LinkType.supported_by, 1.0)],
            "b": [(item_a, LinkType.supported_by, 1.0)],
        }
        items_map = {"a": item_a, "b": item_b}

        # Should not hang
        result = propagate_invalidation(
            item_a,
            find_dependents=lambda item_id: dependents_map.get(item_id, []),
            resolve_item=lambda item_id: items_map.get(item_id),
        )

        # Should complete without infinite loop
        assert isinstance(result, InvalidationResult)
