"""Deep Agents trace sink adapter backed by ContextSeek."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from contextseek.bridges.base import AdapterCapability, AdapterSpec
from contextseek.bridges.compat import DEEPAGENTS_AVAILABLE


@dataclass
class TraceSink:
    """Sink runtime events into ContextSeek as raw trace ContextItems."""

    client: Any  # ContextSeek
    scope: str

    @classmethod
    def spec(cls) -> AdapterSpec:
        return AdapterSpec(
            name="contextseek.deepagents.trace_sink",
            framework="deepagents",
            capabilities=(AdapterCapability.TRACE_SINK,),
            description="Deep Agents trace sink adapter for writing execution traces.",
            required_packages=("deepagents",),
        )

    @classmethod
    def validate_environment(cls) -> tuple[bool, str | None]:
        if DEEPAGENTS_AVAILABLE:
            return True, None
        return (
            False,
            "deepagents package is required for native Deep Agents integration.",
        )

    @classmethod
    def from_client(cls, client: Any, *, scope: str) -> "TraceSink":
        return cls(client=client, scope=scope)

    def write_trace(
        self,
        *,
        task_id: str,
        input_text: str,
        output_text: str,
        tool_calls: list[dict[str, Any]] | None = None,
        feedback: str | None = None,
        duration_ms: int = 0,
        status: str = "success",
    ) -> str:
        """Persist one task trace and return item ID."""
        from contextseek.domain.provenance import SourceType

        content = {
            "input": input_text,
            "output": output_text,
            "tool_calls": tool_calls or [],
            "feedback": feedback,
            "task_id": task_id,
            "duration_ms": duration_ms,
            "status": status,
        }
        item = self.client.add(
            content,
            scope=self.scope,
            source="deepagents_trace",
            source_type=SourceType.trace_extraction,
            tags=["trace", "deepagents"],
        )
        return item.id
