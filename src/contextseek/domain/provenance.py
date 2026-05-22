"""Provenance model — every ContextItem must declare its source."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SourceType(str, Enum):
    """How data entered the system."""

    human_input = "human_input"
    """Direct user entry or annotation."""

    document = "document"
    """Imported from documents or knowledge bases."""

    trace_extraction = "trace_extraction"
    """Distilled from execution traces."""

    agent_inference = "agent_inference"
    """Produced by agent reasoning."""

    distillation = "distillation"
    """Distilled from large corpora."""

    external_api = "external_api"
    """Returned by external systems or tools."""

    merge_result = "merge_result"
    """Produced by merging multiple items."""

    dream_consolidation = "dream_consolidation"
    """Emitted by consolidation dreaming."""

    dream_divergence = "dream_divergence"
    """Emitted by divergence dreaming."""


# source_type → default confidence
SOURCE_TYPE_CONFIDENCE: dict[SourceType, float] = {
    SourceType.human_input: 1.0,
    SourceType.document: 0.8,
    SourceType.trace_extraction: 0.5,
    SourceType.agent_inference: 0.6,
    SourceType.distillation: 0.7,
    SourceType.external_api: 0.5,
    SourceType.merge_result: 0.7,
    SourceType.dream_consolidation: 0.4,
    SourceType.dream_divergence: 0.3,
}


@dataclass(frozen=True)
class Provenance:
    """Source chain — answers where this record came from and why it is trustworthy.

    Provenance is required on every ``ContextItem``. Records without provenance
    must not enter ContextSeek.
    """

    source_type: SourceType
    """Origin channel."""

    source_id: str
    """Origin identifier (document URL / trace id / user id / tool name)."""

    confidence: float = 1.0
    """Confidence score (0.0–1.0)."""

    verified: bool = False
    """Whether a human or external verifier confirmed the record."""

    created_by: str | None = None
    """Creator (user / system / agent id)."""

    context: str | None = None
    """Human-readable source context (e.g. extracted from a failed deploy trace)."""
