"""Link model — directed relationships between ContextItems."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class LinkType(str, Enum):
    """Relation kinds used for both provenance and evolution."""

    # Provenance-oriented
    derived_from = "derived_from"
    """Extracted or derived from another record."""

    supported_by = "supported_by"
    """Corroborated by another record."""

    refuted_by = "refuted_by"
    """Contradicted by another record."""

    # Evolution-oriented
    supersedes = "supersedes"
    """Replaces or updates an older record."""

    merged_from = "merged_from"
    """Produced by merging multiple records."""

    distilled_into = "distilled_into"
    """Distilled into a higher-tier item."""

    # Structural
    related_to = "related_to"
    """Loose associative link."""

    requires = "requires"
    """Dependency / prerequisite."""

    synthesized_from = "synthesized_from"
    """Dreaming synthesized this from multiple items."""


@dataclass(frozen=True)
class Link:
    """Directed edge between ``ContextItem`` records."""

    target_id: str
    """Destination item id."""

    relation: LinkType
    """Edge type."""

    strength: float = 1.0
    """Edge weight for retrieval tuning (0.0–1.0)."""

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
