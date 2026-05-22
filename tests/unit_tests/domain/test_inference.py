"""Tests for stage/stability/provenance inference."""

from contextseek.domain.inference import (
    infer_stage,
    infer_stability,
    infer_confidence,
    build_provenance,
    _is_trace_structure,
)
from contextseek.domain.provenance import SourceType
from contextseek.domain.stages import Stage, Stability


class TestInference:
    def test_infer_stage_human_input(self):
        assert infer_stage(SourceType.human_input, "some text") == Stage.knowledge

    def test_infer_stage_trace(self):
        # Trace extraction with trace structure → raw (awaits extraction pipeline)
        trace_content = {"input": "hi", "output": "hello", "tool_calls": []}
        assert infer_stage(SourceType.trace_extraction, trace_content) == Stage.raw

    def test_infer_stage_agent_inference(self):
        assert infer_stage(SourceType.agent_inference, "inferred fact") == Stage.extracted

    def test_infer_stage_document(self):
        assert infer_stage(SourceType.document, "doc text") == Stage.knowledge

    def test_infer_stability(self):
        assert infer_stability(Stage.raw, SourceType.trace_extraction) == Stability.transient
        assert infer_stability(Stage.knowledge, SourceType.human_input) == Stability.stable
        assert infer_stability(Stage.skill, SourceType.distillation) == Stability.permanent

    def test_infer_confidence(self):
        assert infer_confidence(SourceType.human_input) >= 0.8
        assert infer_confidence(SourceType.agent_inference) < 0.8

    def test_is_trace_structure(self):
        assert _is_trace_structure({"input": "x", "output": "y"}) is True
        assert _is_trace_structure({"random": "dict"}) is False
        assert _is_trace_structure({"unrelated": "keys"}) is False

    def test_build_provenance(self):
        prov = build_provenance(
            source="manual",
            source_type=SourceType.human_input,
        )
        assert prov.source_type == SourceType.human_input
        assert prov.source_id == "manual"
        assert prov.confidence >= 0.8
