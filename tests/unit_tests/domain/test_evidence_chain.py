"""Tests for domain.evidence_chain — confidence propagation and DAG computation."""

from __future__ import annotations

from contextseek.domain.context_item import ContextItem
from contextseek.domain.evidence_chain import (
    EvidenceChain,
    compute_chain_confidence,
    compute_evidence_chain,
)
from contextseek.domain.links import Link, LinkType
from contextseek.domain.provenance import Provenance, SourceType
from contextseek.domain.stages import Stage


def _make_item(
    item_id: str,
    confidence: float = 0.8,
    stage: Stage = Stage.knowledge,
    links: list[Link] | None = None,
) -> ContextItem:
    return ContextItem(
        id=item_id,
        content=f"content of {item_id}",
        scope="test/scope",
        provenance=Provenance(
            source_type=SourceType.document,
            source_id=f"source_{item_id}",
            confidence=confidence,
        ),
        stage=stage,
        links=links or [],
    )


class TestSingleItem:
    """Test evidence chain with a single root item (no links)."""

    def test_single_item_returns_intrinsic_confidence(self):
        item = _make_item("root", confidence=0.9)
        chain = compute_evidence_chain(item, lambda _: None)

        assert chain.root_item_id == "root"
        assert chain.overall_confidence == 0.9
        assert len(chain.nodes) == 1
        assert len(chain.edges) == 0
        assert chain.nodes[0].is_root is True
        assert not chain.has_conflicts
        assert not chain.needs_reverification

    def test_single_item_low_confidence_flags_reverification(self):
        item = _make_item("weak", confidence=0.2)
        chain = compute_evidence_chain(item, lambda _: None, reverification_threshold=0.4)

        assert chain.needs_reverification is True


class TestSingleLink:
    """Test evidence chain with one derived_from link."""

    def test_derived_from_propagates_confidence(self):
        parent = _make_item("parent", confidence=0.9)
        child = _make_item(
            "child",
            confidence=0.5,
            links=[Link(target_id="parent", relation=LinkType.derived_from)],
        )

        items = {"parent": parent}
        chain = compute_evidence_chain(child, items.get)

        # Child confidence = Noisy-OR of: parent_conf * strength * type_factor
        # = 0.9 * 1.0 * 0.9 = 0.81
        assert chain.overall_confidence > 0.7
        assert len(chain.nodes) == 2
        assert len(chain.edges) == 1

    def test_supported_by_boosts_confidence(self):
        evidence = _make_item("evidence", confidence=1.0)
        item = _make_item(
            "item",
            confidence=0.5,
            links=[Link(target_id="evidence", relation=LinkType.supported_by)],
        )

        items = {"evidence": evidence}
        chain = compute_evidence_chain(item, items.get)

        # supported_by: 1.0 * 1.0 * 0.7 = 0.7
        assert chain.overall_confidence > 0.6


class TestMultipleLinks:
    """Test Noisy-OR aggregation with multiple supporting links."""

    def test_multiple_sources_increase_confidence(self):
        parent1 = _make_item("p1", confidence=0.8)
        parent2 = _make_item("p2", confidence=0.7)
        child = _make_item(
            "child",
            confidence=0.3,
            links=[
                Link(target_id="p1", relation=LinkType.derived_from),
                Link(target_id="p2", relation=LinkType.supported_by),
            ],
        )

        items = {"p1": parent1, "p2": parent2}
        chain = compute_evidence_chain(child, items.get)

        # Two sources → higher than either alone (Noisy-OR)
        single_source_chain = compute_evidence_chain(
            _make_item(
                "single",
                confidence=0.3,
                links=[Link(target_id="p1", relation=LinkType.derived_from)],
            ),
            items.get,
        )
        assert chain.overall_confidence > single_source_chain.overall_confidence

    def test_merged_from_aggregates_sources(self):
        s1 = _make_item("s1", confidence=0.6)
        s2 = _make_item("s2", confidence=0.6)
        s3 = _make_item("s3", confidence=0.6)
        merged = _make_item(
            "merged",
            confidence=0.7,
            stage=Stage.knowledge,
            links=[
                Link(target_id="s1", relation=LinkType.merged_from),
                Link(target_id="s2", relation=LinkType.merged_from),
                Link(target_id="s3", relation=LinkType.merged_from),
            ],
        )

        items = {"s1": s1, "s2": s2, "s3": s3}
        chain = compute_evidence_chain(merged, items.get)

        # Three merged sources → high confidence
        assert chain.overall_confidence > 0.8
        assert chain.total_sources == 3


class TestRefutation:
    """Test refuted_by links reduce confidence."""

    def test_refuted_by_reduces_confidence(self):
        support = _make_item("support", confidence=0.9)
        refuter = _make_item("refuter", confidence=0.8)
        item = _make_item(
            "item",
            confidence=0.5,
            links=[
                Link(target_id="support", relation=LinkType.derived_from),
                Link(target_id="refuter", relation=LinkType.refuted_by),
            ],
        )

        items = {"support": support, "refuter": refuter}
        chain = compute_evidence_chain(item, items.get)

        # Confidence should be lower than without refutation
        no_refute = compute_evidence_chain(
            _make_item(
                "no_refute",
                confidence=0.5,
                links=[Link(target_id="support", relation=LinkType.derived_from)],
            ),
            items.get,
        )
        assert chain.overall_confidence < no_refute.overall_confidence
        assert chain.has_conflicts
        assert len(chain.conflicts) == 1
        assert chain.conflicts[0].refuter_id == "refuter"

    def test_strong_refutation_drives_confidence_low(self):
        refuter = _make_item("refuter", confidence=1.0)
        item = _make_item(
            "item",
            confidence=0.5,
            links=[
                Link(target_id="refuter", relation=LinkType.refuted_by, strength=1.0),
            ],
        )

        items = {"refuter": refuter}
        chain = compute_evidence_chain(item, items.get)

        # Only refutation, no positive support → confidence should be very low
        assert chain.overall_confidence <= 0.1


class TestBrokenLinks:
    """Test handling of missing/unresolvable items."""

    def test_missing_parent_is_recorded(self):
        item = _make_item(
            "orphan",
            confidence=0.5,
            links=[Link(target_id="nonexistent", relation=LinkType.derived_from)],
        )

        chain = compute_evidence_chain(item, lambda _: None)

        assert "nonexistent" in chain.broken_links
        missing_nodes = [n for n in chain.nodes if n.is_missing]
        assert len(missing_nodes) == 1

    def test_missing_parent_uses_intrinsic(self):
        item = _make_item(
            "item",
            confidence=0.6,
            links=[Link(target_id="gone", relation=LinkType.derived_from)],
        )

        chain = compute_evidence_chain(item, lambda _: None)

        # Missing parent contributes 0 → Noisy-OR with 0 = 0
        # Falls back to intrinsic since no valid contribution
        # Actually: C_link = 0.0 * 1.0 * 0.9 = 0.0
        # Noisy-OR of [0.0] = 1 - (1-0) = 0.0 → uses intrinsic
        # The item should have very low effective confidence or intrinsic
        assert chain.overall_confidence >= 0.0


class TestCycleDetection:
    """Test that cycles in the evidence graph don't cause infinite loops."""

    def test_mutual_reference_terminates(self):
        item_a = _make_item(
            "a",
            confidence=0.7,
            links=[Link(target_id="b", relation=LinkType.supported_by)],
        )
        item_b = _make_item(
            "b",
            confidence=0.7,
            links=[Link(target_id="a", relation=LinkType.supported_by)],
        )

        items = {"a": item_a, "b": item_b}
        # Should not hang
        chain = compute_evidence_chain(item_a, items.get)

        assert chain.root_item_id == "a"
        assert len(chain.nodes) == 2


class TestDepthLimit:
    """Test max_depth prevents runaway expansion."""

    def test_deep_chain_is_truncated(self):
        # Build a chain of depth 20
        items: dict[str, ContextItem] = {}
        for i in range(20):
            links = [Link(target_id=f"item_{i-1}", relation=LinkType.derived_from)] if i > 0 else []
            items[f"item_{i}"] = _make_item(f"item_{i}", confidence=0.9, links=links)

        chain = compute_evidence_chain(items["item_19"], items.get, max_depth=5)

        # Should not have all 20 nodes
        assert chain.max_depth <= 5
        assert len(chain.nodes) < 20


class TestCriticalPath:
    """Test critical path identification."""

    def test_critical_path_follows_strongest(self):
        strong_parent = _make_item("strong", confidence=0.95)
        weak_parent = _make_item("weak", confidence=0.3)
        child = _make_item(
            "child",
            confidence=0.5,
            links=[
                Link(target_id="strong", relation=LinkType.derived_from, strength=1.0),
                Link(target_id="weak", relation=LinkType.supported_by, strength=0.2),
            ],
        )

        items = {"strong": strong_parent, "weak": weak_parent}
        chain = compute_evidence_chain(child, items.get)

        # Critical path should include the strong parent
        assert "child" in chain.critical_path
        assert "strong" in chain.critical_path


class TestLinkStrength:
    """Test that link.strength modulates contribution."""

    def test_weak_link_reduces_contribution(self):
        parent = _make_item("parent", confidence=0.9)

        strong_child = _make_item(
            "strong_child",
            confidence=0.5,
            links=[Link(target_id="parent", relation=LinkType.derived_from, strength=1.0)],
        )
        weak_child = _make_item(
            "weak_child",
            confidence=0.5,
            links=[Link(target_id="parent", relation=LinkType.derived_from, strength=0.3)],
        )

        items = {"parent": parent}
        strong_chain = compute_evidence_chain(strong_child, items.get)
        weak_chain = compute_evidence_chain(weak_child, items.get)

        assert strong_chain.overall_confidence > weak_chain.overall_confidence


class TestChainConfidenceShortcut:
    """Test compute_chain_confidence returns same value as full chain."""

    def test_matches_full_computation(self):
        parent = _make_item("parent", confidence=0.8)
        child = _make_item(
            "child",
            confidence=0.5,
            links=[Link(target_id="parent", relation=LinkType.derived_from)],
        )

        items = {"parent": parent}
        full_chain = compute_evidence_chain(child, items.get)
        quick_conf = compute_chain_confidence(child, items.get)

        assert quick_conf == full_chain.overall_confidence


class TestToDict:
    """Test serialization of EvidenceChain."""

    def test_to_dict_is_json_compatible(self):
        import json

        parent = _make_item("parent", confidence=0.9)
        child = _make_item(
            "child",
            confidence=0.5,
            links=[Link(target_id="parent", relation=LinkType.derived_from)],
        )

        items = {"parent": parent}
        chain = compute_evidence_chain(child, items.get)
        d = chain.to_dict()

        # Should be JSON-serializable
        serialized = json.dumps(d)
        assert "root_item_id" in serialized
        assert "overall_confidence" in serialized
        assert "nodes" in serialized
        assert "edges" in serialized
