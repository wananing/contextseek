"""Centralized configurable LLM prompt templates and builders."""

from __future__ import annotations

from dataclasses import dataclass

from contextseek.domain.context_item import ContextItem


@dataclass(frozen=True)
class LLMPromptTemplates:
    summarizer_abstract_template: str = (
        "Extract the core information from the following content and summarise it "
        "in a single sentence (at most {char_budget} characters). "
        "If the content is a conversation, distil the key facts and omit pleasantries "
        "and redundant phrasing. Output only the summary, no explanation:\n\n{content}"
    )
    summarizer_summary_template: str = (
        "Distil the following content into a concise summary (at most {char_budget} "
        "characters). If the content is a conversation, retain all key information "
        "and strip redundant phrasing. Output only the distilled text, no explanation:"
        "\n\n{content}"
    )
    retrieval_relevance_template: str = "\n".join(
        [
            "Score relevance from 0.0 to 1.0.",
            'Return JSON only: {{"score": <float>}}.',
            "Query: {query}",
            "Passage: {content}",
        ]
    )
    conflict_judge_template: str = "\n".join(
        [
            "Classify relation between two statements.",
            "Choose one label: near_duplicate, contradiction, none.",
            'Return JSON only: {{"label":"...","reason":"..."}}.',
            "Token overlap: {overlap}",
            "A: {new_text}",
            "B: {existing_text}",
        ]
    )
    stage_classifier_template: str = "\n".join(
        [
            "Infer initial stage for a context item.",
            "Allowed values: raw, extracted, knowledge, skill.",
            'Return JSON only: {{"stage":"..."}}.',
            "source_type: {source_type}",
            "default_stage: {default_stage}",
            "content: {content_text}",
        ]
    )
    feedback_tag_template: str = "\n".join(
        [
            "Classify feedback reason and suggest one action tag.",
            "Allowed tags: needs_review, needs_reverification, evolution_candidate, none.",
            'Return JSON only: {{"tag":"..."}}.',
            "item_stage: {stage}",
            "reason: {reason}",
        ]
    )
    merge_synthesis_template: str = "\n".join(
        [
            "Synthesize one consolidated knowledge statement from these items.",
            "Return plain text only.",
            "{items}",
        ]
    )
    distill_candidate_template: str = "\n".join(
        [
            "Is this knowledge item a reusable procedural skill?",
            'Return JSON only: {{"distill": true|false}}.',
            "content: {content_text}",
            "tags: {tags}",
        ]
    )
    distill_render_template: str = "\n".join(
        [
            "Create a prompt skill payload from this knowledge item.",
            "Return JSON only with keys: name, description, body.",
            "content: {content_text}",
            "tags: {tags}",
        ]
    )
    dream_consolidation_template: str = "\n".join(
        [
            "Summarize the shared reusable pattern from these context items.",
            "Return one concise sentence only.",
            "{items}",
        ]
    )
    dream_divergence_template: str = "\n".join(
        [
            "Here are two observations from different domains:",
            "A: {a_text}",
            "B: {b_text}",
            "Speculate: how might they be connected? Generate a concise hypothesis.",
        ]
    )


DEFAULT_LLM_PROMPTS = LLMPromptTemplates()


def _render(template: str, **kwargs: str | int | float) -> str:
    try:
        return template.format(**kwargs)
    except Exception:
        return template


def summarizer_abstract_prompt(
    *,
    char_budget: int,
    content: str,
    templates: LLMPromptTemplates | None = None,
) -> str:
    t = templates or DEFAULT_LLM_PROMPTS
    return _render(
        t.summarizer_abstract_template,
        char_budget=char_budget,
        content=content,
    )


def summarizer_summary_prompt(
    *,
    char_budget: int,
    content: str,
    templates: LLMPromptTemplates | None = None,
) -> str:
    t = templates or DEFAULT_LLM_PROMPTS
    return _render(
        t.summarizer_summary_template,
        char_budget=char_budget,
        content=content,
    )


def retrieval_relevance_prompt(
    *,
    query: str,
    content: str,
    templates: LLMPromptTemplates | None = None,
) -> str:
    t = templates or DEFAULT_LLM_PROMPTS
    return _render(
        t.retrieval_relevance_template,
        query=query[:400],
        content=content[:2000],
    )


def conflict_judge_prompt(
    *,
    new_text: str,
    existing_text: str,
    overlap: float,
    templates: LLMPromptTemplates | None = None,
) -> str:
    t = templates or DEFAULT_LLM_PROMPTS
    return _render(
        t.conflict_judge_template,
        overlap=f"{overlap:.3f}",
        new_text=new_text[:800],
        existing_text=existing_text[:800],
    )


def stage_classifier_prompt(
    *,
    source_type: str,
    default_stage: str,
    content_text: str,
    templates: LLMPromptTemplates | None = None,
) -> str:
    t = templates or DEFAULT_LLM_PROMPTS
    return _render(
        t.stage_classifier_template,
        source_type=source_type,
        default_stage=default_stage,
        content_text=content_text[:1200],
    )


def feedback_tag_prompt(
    *,
    stage: str,
    reason: str,
    templates: LLMPromptTemplates | None = None,
) -> str:
    t = templates or DEFAULT_LLM_PROMPTS
    return _render(
        t.feedback_tag_template,
        stage=stage,
        reason=reason[:800],
    )


def merge_synthesis_prompt(
    *,
    cluster_texts: list[str],
    templates: LLMPromptTemplates | None = None,
) -> str:
    t = templates or DEFAULT_LLM_PROMPTS
    item_lines = [f"{idx}. {text[:600]}" for idx, text in enumerate(cluster_texts[:8], start=1)]
    return _render(t.merge_synthesis_template, items="\n".join(item_lines))


def distill_candidate_prompt(
    *,
    item: ContextItem,
    templates: LLMPromptTemplates | None = None,
) -> str:
    t = templates or DEFAULT_LLM_PROMPTS
    return _render(
        t.distill_candidate_template,
        content_text=item.content_text[:1200],
        tags=", ".join(item.tags[:20]),
    )


def distill_render_prompt(
    *,
    item: ContextItem,
    templates: LLMPromptTemplates | None = None,
) -> str:
    t = templates or DEFAULT_LLM_PROMPTS
    return _render(
        t.distill_render_template,
        content_text=item.content_text[:1600],
        tags=", ".join(item.tags[:20]),
    )


def dream_consolidation_prompt(
    *,
    cluster_items: list[ContextItem],
    templates: LLMPromptTemplates | None = None,
) -> str:
    t = templates or DEFAULT_LLM_PROMPTS
    item_lines = [f"{idx}. {item.content_text[:300]}" for idx, item in enumerate(cluster_items[:6], start=1)]
    return _render(t.dream_consolidation_template, items="\n".join(item_lines))


def dream_divergence_prompt(
    *,
    a: ContextItem,
    b: ContextItem,
    templates: LLMPromptTemplates | None = None,
) -> str:
    t = templates or DEFAULT_LLM_PROMPTS
    return _render(
        t.dream_divergence_template,
        a_text=a.content_text[:300],
        b_text=b.content_text[:300],
    )
