"""Evidence Chain — DAG-based confidence propagation and traceability.

Computes propagated confidence along the evidence graph using Noisy-OR
aggregation for supporting links and additive penalty for refutations.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

from contextseek.domain.context_item import ContextItem
from contextseek.domain.links import LinkType
from contextseek.domain.stages import Stage


# ═══════════════════════════════════════════════════════════════════════════════
# Type Factors — how much confidence propagates through each link type
# ═══════════════════════════════════════════════════════════════════════════════

TYPE_FACTOR: dict[LinkType, float] = {
    LinkType.derived_from: 0.9,
    LinkType.supported_by: 0.7,
    LinkType.merged_from: 0.85,
    LinkType.distilled_into: 0.95,
    LinkType.refuted_by: -0.5,
    LinkType.supersedes: 0.0,
    LinkType.related_to: 0.0,
    LinkType.requires: 0.0,
}

# Link types that propagate positive confidence
_POSITIVE_TYPES = frozenset({
    LinkType.derived_from,
    LinkType.supported_by,
    LinkType.merged_from,
    LinkType.distilled_into,
})

# Link types that reduce confidence
_NEGATIVE_TYPES = frozenset({LinkType.refuted_by})

# All link types followed during evidence chain traversal
_TRACEABLE_TYPES = _POSITIVE_TYPES | _NEGATIVE_TYPES


# ═══════════════════════════════════════════════════════════════════════════════
# Data Structures
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ChainNode:
    """A node in the evidence chain DAG."""

    item_id: str
    intrinsic_confidence: float
    effective_confidence: float
    stage: Stage
    depth: int
    is_root: bool
    is_missing: bool = False


@dataclass(frozen=True)
class ChainEdge:
    """An edge in the evidence chain DAG."""

    source_id: str
    target_id: str
    relation: LinkType
    strength: float
    contribution: float


@dataclass(frozen=True)
class ConflictReport:
    """A refutation conflict detected in the chain."""

    item_id: str
    refuter_id: str
    refutation_strength: float
    net_confidence_impact: float


@dataclass(frozen=True)
class EvidenceChain:
    """Complete evidence chain for a single ContextItem."""

    root_item_id: str
    nodes: list[ChainNode]
    edges: list[ChainEdge]

    overall_confidence: float
    max_depth: int
    total_sources: int

    critical_path: list[str]
    critical_path_confidence: float

    conflicts: list[ConflictReport]
    has_conflicts: bool

    broken_links: list[str]
    needs_reverification: bool

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "root_item_id": self.root_item_id,
            "nodes": [
                {
                    "item_id": n.item_id,
                    "intrinsic_confidence": n.intrinsic_confidence,
                    "effective_confidence": n.effective_confidence,
                    "stage": n.stage.value,
                    "depth": n.depth,
                    "is_root": n.is_root,
                    "is_missing": n.is_missing,
                }
                for n in self.nodes
            ],
            "edges": [
                {
                    "source_id": e.source_id,
                    "target_id": e.target_id,
                    "relation": e.relation.value,
                    "strength": e.strength,
                    "contribution": e.contribution,
                }
                for e in self.edges
            ],
            "overall_confidence": self.overall_confidence,
            "max_depth": self.max_depth,
            "total_sources": self.total_sources,
            "critical_path": self.critical_path,
            "critical_path_confidence": self.critical_path_confidence,
            "conflicts": [
                {
                    "item_id": c.item_id,
                    "refuter_id": c.refuter_id,
                    "refutation_strength": c.refutation_strength,
                    "net_confidence_impact": c.net_confidence_impact,
                }
                for c in self.conflicts
            ],
            "has_conflicts": self.has_conflicts,
            "broken_links": self.broken_links,
            "needs_reverification": self.needs_reverification,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Core Algorithm
# ═══════════════════════════════════════════════════════════════════════════════


def compute_evidence_chain(
    root_item: ContextItem,
    resolver: Callable[[str], ContextItem | None],
    *,
    max_depth: int = 10,
    reverification_threshold: float = 0.4,
) -> EvidenceChain:
    """Compute the full evidence chain DAG for a ContextItem.

    Args:
        root_item: The starting item to compute the chain for.
        resolver: Callable that resolves an item_id to a ContextItem (or None).
        max_depth: Maximum traversal depth to prevent runaway expansion.
        reverification_threshold: Confidence below which needs_reverification is set.

    Returns:
        A complete EvidenceChain with propagated confidence scores.
    """
    # Phase 1: BFS to collect all reachable nodes and edges
    items: dict[str, ContextItem] = {root_item.id: root_item}
    depths: dict[str, int] = {root_item.id: 0}
    missing_ids: set[str] = set()
    raw_edges: list[tuple[str, str, LinkType, float]] = []  # (source, target, type, strength)

    queue: deque[tuple[str, int]] = deque([(root_item.id, 0)])
    visited: set[str] = {root_item.id}

    while queue:
        current_id, depth = queue.popleft()
        if depth >= max_depth:
            continue

        current = items.get(current_id)
        if current is None:
            continue

        for link in current.links:
            factor = TYPE_FACTOR.get(link.relation, 0.0)
            if factor == 0.0:
                continue

            raw_edges.append((current_id, link.target_id, link.relation, link.strength))

            if link.target_id in visited:
                continue
            visited.add(link.target_id)

            target = resolver(link.target_id)
            if target is None:
                missing_ids.add(link.target_id)
                depths[link.target_id] = depth + 1
            else:
                items[link.target_id] = target
                depths[link.target_id] = depth + 1
                queue.append((link.target_id, depth + 1))

    # Phase 2: Topological sort (leaves first) for bottom-up confidence computation
    # Build adjacency: for confidence, we need to know for each node,
    # which edges POINT TO it (i.e., the node is a target)
    # But in our model, links go from child -> parent (derived_from means
    # "I am derived from parent"). So an item's links point to its SOURCES.
    # For bottom-up computation: roots (no outgoing evidence links) have intrinsic confidence.
    # Children compute from their targets (parents).

    # Determine which nodes are roots (have no outgoing traceable links to resolved items)
    has_parents: set[str] = set()
    for source_id, target_id, rel, _strength in raw_edges:
        if target_id not in missing_ids:
            has_parents.add(source_id)

    # Topological ordering via Kahn's algorithm on the DAG
    # Direction: parent -> child (reversed from link direction)
    # in_degree: how many parents each node depends on
    children_of: dict[str, list[str]] = {}  # parent -> [children]
    in_degree: dict[str, int] = {nid: 0 for nid in items}
    in_degree.update({mid: 0 for mid in missing_ids})

    for source_id, target_id, rel, _strength in raw_edges:
        if rel in _POSITIVE_TYPES | _NEGATIVE_TYPES:
            # source depends on target (source is child, target is parent)
            children_of.setdefault(target_id, []).append(source_id)
            if source_id in in_degree:
                in_degree[source_id] += 1

    # Start from roots (nodes with in_degree 0 — no parents)
    topo_queue: deque[str] = deque()
    for nid, deg in in_degree.items():
        if deg == 0:
            topo_queue.append(nid)

    topo_order: list[str] = []
    while topo_queue:
        nid = topo_queue.popleft()
        topo_order.append(nid)
        for child in children_of.get(nid, []):
            if child in in_degree:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    topo_queue.append(child)

    # Nodes not in topo_order are in cycles — use intrinsic confidence
    all_node_ids = set(items.keys()) | missing_ids
    cycle_nodes = all_node_ids - set(topo_order)

    # Phase 3: Compute effective confidence bottom-up
    effective: dict[str, float] = {}

    # Missing nodes get 0.0
    for mid in missing_ids:
        effective[mid] = 0.0

    # Cycle nodes fall back to intrinsic
    for cid in cycle_nodes:
        item = items.get(cid)
        effective[cid] = item.provenance.confidence if item else 0.0

    # Process in topological order (parents before children)
    for nid in topo_order:
        if nid in effective:
            continue  # already handled (missing/cycle)

        item = items.get(nid)
        if item is None:
            effective[nid] = 0.0
            continue

        # Gather incoming links (this item's links point to its parents)
        positive_contributions: list[float] = []
        negative_contributions: list[float] = []

        for source_id, target_id, rel, strength in raw_edges:
            if source_id != nid:
                continue
            parent_conf = effective.get(target_id, 0.0)
            factor = TYPE_FACTOR.get(rel, 0.0)
            contribution = parent_conf * strength * abs(factor)

            if rel in _POSITIVE_TYPES:
                positive_contributions.append(contribution)
            elif rel in _NEGATIVE_TYPES:
                negative_contributions.append(contribution)

        if not positive_contributions and not negative_contributions:
            # Root node — use intrinsic confidence
            effective[nid] = item.provenance.confidence
        else:
            # Noisy-OR for positive
            if positive_contributions:
                product = 1.0
                for c in positive_contributions:
                    product *= (1.0 - min(c, 1.0))
                c_positive = 1.0 - product
            else:
                c_positive = item.provenance.confidence

            # Sum for negative (capped at 1.0)
            c_negative = min(sum(negative_contributions), 1.0)

            effective[nid] = max(0.0, min(1.0, c_positive - c_negative))

    # Phase 4: Build edges with contribution values
    chain_edges: list[ChainEdge] = []
    for source_id, target_id, rel, strength in raw_edges:
        parent_conf = effective.get(target_id, 0.0)
        factor = TYPE_FACTOR.get(rel, 0.0)
        contribution = parent_conf * strength * abs(factor)
        if rel in _NEGATIVE_TYPES:
            contribution = -contribution
        chain_edges.append(ChainEdge(
            source_id=source_id,
            target_id=target_id,
            relation=rel,
            strength=strength,
            contribution=round(contribution, 6),
        ))

    # Phase 5: Build nodes
    chain_nodes: list[ChainNode] = []
    for nid, item in items.items():
        chain_nodes.append(ChainNode(
            item_id=nid,
            intrinsic_confidence=item.provenance.confidence,
            effective_confidence=round(effective.get(nid, item.provenance.confidence), 6),
            stage=item.stage,
            depth=depths.get(nid, 0),
            is_root=nid not in has_parents,
        ))
    for mid in missing_ids:
        chain_nodes.append(ChainNode(
            item_id=mid,
            intrinsic_confidence=0.0,
            effective_confidence=0.0,
            stage=Stage.raw,
            depth=depths.get(mid, 0),
            is_root=True,
            is_missing=True,
        ))

    # Phase 6: Critical path — greedy walk from root following max positive contribution
    critical_path = [root_item.id]
    critical_conf = effective.get(root_item.id, root_item.provenance.confidence)
    current_id = root_item.id
    path_visited: set[str] = {current_id}

    while True:
        # Find the link from current with highest positive contribution
        best_target: str | None = None
        best_contribution = 0.0
        for edge in chain_edges:
            if edge.source_id == current_id and edge.contribution > best_contribution:
                if edge.target_id not in path_visited:
                    best_target = edge.target_id
                    best_contribution = edge.contribution
        if best_target is None:
            break
        critical_path.append(best_target)
        path_visited.add(best_target)
        current_id = best_target

    # Phase 7: Conflict detection
    conflicts: list[ConflictReport] = []
    for edge in chain_edges:
        if edge.relation == LinkType.refuted_by:
            conflicts.append(ConflictReport(
                item_id=edge.source_id,
                refuter_id=edge.target_id,
                refutation_strength=edge.strength,
                net_confidence_impact=round(abs(edge.contribution), 6),
            ))

    # Phase 8: Assemble result
    overall_confidence = round(effective.get(root_item.id, root_item.provenance.confidence), 6)
    actual_max_depth = max(depths.values()) if depths else 0
    root_nodes = [n for n in chain_nodes if n.is_root and not n.is_missing]

    return EvidenceChain(
        root_item_id=root_item.id,
        nodes=chain_nodes,
        edges=chain_edges,
        overall_confidence=overall_confidence,
        max_depth=actual_max_depth,
        total_sources=len(root_nodes),
        critical_path=critical_path,
        critical_path_confidence=round(critical_conf, 6),
        conflicts=conflicts,
        has_conflicts=len(conflicts) > 0,
        broken_links=sorted(missing_ids),
        needs_reverification=overall_confidence < reverification_threshold,
    )


def compute_chain_confidence(
    item: ContextItem,
    resolver: Callable[[str], ContextItem | None],
    *,
    max_depth: int = 10,
) -> float:
    """Quick confidence computation without building the full DAG.

    Lighter than compute_evidence_chain() — only computes the root's
    effective confidence without constructing the full result object.
    """
    chain = compute_evidence_chain(item, resolver, max_depth=max_depth)
    return chain.overall_confidence
