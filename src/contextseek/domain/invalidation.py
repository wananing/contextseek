"""Invalidation propagation — confidence degradation along evidence chains.

When a source item is deleted or degraded, dependents that rely on it
should have their effective_confidence recomputed. Items that drop below
the reverification threshold are flagged with a "needs_reverification" tag.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Callable

from contextseek.domain.context_item import ContextItem
from contextseek.domain.evidence_chain import (
    TYPE_FACTOR,
    _POSITIVE_TYPES,
    _NEGATIVE_TYPES,
)
from contextseek.domain.links import LinkType


@dataclass(frozen=True)
class DegradedItem:
    """Record of a single item whose confidence was degraded."""

    item_id: str
    old_confidence: float
    new_confidence: float


@dataclass(frozen=True)
class InvalidationResult:
    """Result of invalidation propagation from a deleted/degraded source."""

    degraded_items: list[DegradedItem]
    reverification_needed: list[str]
    propagation_depth: int


def propagate_invalidation(
    deleted_item: ContextItem,
    find_dependents: Callable[[str], list[tuple[ContextItem, LinkType, float]]],
    resolve_item: Callable[[str], ContextItem | None],
    *,
    reverification_threshold: float = 0.4,
    max_depth: int = 10,
) -> InvalidationResult:
    """Propagate confidence degradation from a deleted/degraded source.

    When an item is deleted, all items that reference it via evidence links
    (derived_from, merged_from, distilled_into) need their confidence
    recomputed.

    Args:
        deleted_item: The item that was deleted or degraded.
        find_dependents: Given an item_id, returns list of
            (dependent_item, link_relation, link_strength) tuples — i.e.,
            items whose links contain target_id == item_id.
        resolve_item: Resolves an item_id to ContextItem (for looking up
            other parents of a dependent).
        reverification_threshold: Confidence below which to flag.
        max_depth: Maximum propagation depth.

    Returns:
        InvalidationResult describing all affected items.
    """
    degraded: list[DegradedItem] = []
    needs_reverification: list[str] = []
    max_depth_reached = 0

    # BFS propagation
    queue: deque[tuple[str, int]] = deque([(deleted_item.id, 0)])
    visited: set[str] = {deleted_item.id}

    while queue:
        current_id, depth = queue.popleft()
        if depth >= max_depth:
            continue

        max_depth_reached = max(max_depth_reached, depth)
        dependents = find_dependents(current_id)

        for dependent, link_relation, link_strength in dependents:
            if dependent.id in visited:
                continue
            visited.add(dependent.id)

            # Compute old effective confidence (what the item had before)
            old_conf = (
                dependent.effective_confidence
                if dependent.effective_confidence is not None
                else dependent.provenance.confidence
            )

            # Recompute confidence excluding the deleted source
            new_conf = _recompute_without_source(dependent, current_id, resolve_item)

            if new_conf < old_conf:
                degraded.append(
                    DegradedItem(
                        item_id=dependent.id,
                        old_confidence=round(old_conf, 6),
                        new_confidence=round(new_conf, 6),
                    )
                )

                if new_conf < reverification_threshold:
                    needs_reverification.append(dependent.id)

                # Continue propagation if this item also degraded significantly
                if old_conf - new_conf > 0.05:
                    queue.append((dependent.id, depth + 1))

    return InvalidationResult(
        degraded_items=degraded,
        reverification_needed=needs_reverification,
        propagation_depth=max_depth_reached,
    )


def _recompute_without_source(
    item: ContextItem,
    excluded_id: str,
    resolve_item: Callable[[str], ContextItem | None],
) -> float:
    """Recompute effective confidence for an item excluding a specific source.

    Uses the same Noisy-OR formula as compute_evidence_chain but skips
    links pointing to the excluded (deleted) item.
    """
    positive_contributions: list[float] = []
    negative_contributions: list[float] = []

    for link in item.links:
        if link.target_id == excluded_id:
            continue

        factor = TYPE_FACTOR.get(link.relation, 0.0)
        if factor == 0.0:
            continue

        # Resolve the parent to get its confidence
        parent = resolve_item(link.target_id)
        if parent is None:
            continue
        if parent.is_deleted:
            continue

        parent_conf = (
            parent.effective_confidence
            if parent.effective_confidence is not None
            else parent.provenance.confidence
        )

        contribution = parent_conf * link.strength * abs(factor)

        if link.relation in _POSITIVE_TYPES:
            positive_contributions.append(contribution)
        elif link.relation in _NEGATIVE_TYPES:
            negative_contributions.append(contribution)

    if not positive_contributions and not negative_contributions:
        # No surviving parents — fall back to intrinsic
        return item.provenance.confidence

    # Noisy-OR for positive
    if positive_contributions:
        product = 1.0
        for c in positive_contributions:
            product *= 1.0 - min(c, 1.0)
        c_positive = 1.0 - product
    else:
        c_positive = item.provenance.confidence

    # Sum for negative
    c_negative = min(sum(negative_contributions), 1.0)

    return max(0.0, min(1.0, c_positive - c_negative))
