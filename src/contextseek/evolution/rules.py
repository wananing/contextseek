"""Evolution rules — define conditions for Stage transitions."""

from __future__ import annotations

from dataclasses import dataclass

from contextseek.domain.links import LinkType
from contextseek.domain.stages import Stage


@dataclass(frozen=True)
class EvolutionRule:
    """A rule that triggers a stage transition.

    Attributes:
        name: Human-readable rule name.
        source_stage: Items at this stage are candidates.
        target_stage: Stage to promote to on trigger.
        link_type: LinkType to record on the new item.
        min_age_seconds: Minimum age before eligible.
        min_similar_count: How many similar items needed (for convergence).
        min_success_rate: Minimum success rate (for distillation).
        min_use_count: Minimum use count (for distillation).
        content_filter: Only apply to items whose content matches (e.g. has trace structure).
    """

    name: str
    source_stage: Stage
    target_stage: Stage
    link_type: LinkType
    min_age_seconds: int = 0
    min_similar_count: int = 1
    min_success_rate: float = 0.0
    min_use_count: int = 0
    content_filter: str | None = None  # "trace_structure" | "procedure" | None


DEFAULT_RULES: list[EvolutionRule] = [
    EvolutionRule(
        name="extract_from_trace",
        source_stage=Stage.raw,
        target_stage=Stage.extracted,
        link_type=LinkType.derived_from,
        min_age_seconds=3600,  # 1 hour
        content_filter="trace_structure",
    ),
    EvolutionRule(
        name="converge_to_knowledge",
        source_stage=Stage.extracted,
        target_stage=Stage.knowledge,
        link_type=LinkType.merged_from,
        min_similar_count=3,
    ),
    EvolutionRule(
        name="distill_to_skill",
        source_stage=Stage.knowledge,
        target_stage=Stage.skill,
        link_type=LinkType.distilled_into,
        min_success_rate=0.8,
        min_use_count=10,
        content_filter="procedure",
    ),
]
