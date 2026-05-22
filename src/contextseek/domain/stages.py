"""Stage and Stability enums for the ContextItem evolution lifecycle."""

from __future__ import annotations

from enum import Enum


class Stage(str, Enum):
    """Evolution stage — maturity of data inside ContextSeek.

    raw → extracted → knowledge → skill
    """

    raw = "raw"
    """Raw ingest, unprocessed. Sources: user writes, traces, imports."""

    extracted = "extracted"
    """Conclusions or patterns mined from raw inputs. Source: TraceExtractor."""

    knowledge = "knowledge"
    """Stable knowledge validated or corroborated. Sources: convergence, human review, authoritative docs."""

    skill = "skill"
    """Distilled reusable capability. Source: SkillDistiller."""


class Stability(str, Enum):
    """Lifecycle policy — how long data is expected to live."""

    ephemeral = "ephemeral"
    """Session-scoped; expires when the task ends."""

    transient = "transient"
    """Normal decay (default)."""

    stable = "stable"
    """Long retention with very slow decay."""

    permanent = "permanent"
    """No decay; removed only manually."""


STAGE_DEFAULT_STABILITY: dict[Stage, Stability] = {
    Stage.raw: Stability.transient,
    Stage.extracted: Stability.transient,
    Stage.knowledge: Stability.stable,
    Stage.skill: Stability.permanent,
}

STAGE_CONFIDENCE: dict[Stage, float] = {
    Stage.raw: 0.3,
    Stage.extracted: 0.6,
    Stage.knowledge: 0.85,
    Stage.skill: 1.0,
}
