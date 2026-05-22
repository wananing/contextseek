"""Agent adapter protocol — shared between baseline and ContextSeek adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class AgentAdapter(Protocol):
    """Protocol for task-running adapters (baseline / contextseek / evolve)."""

    adapter_name: str

    def run_task(self, task_id: int, trial: int = 0) -> "TaskResult": ...


@dataclass
class TaskResult:
    """Result of one tau-bench task run."""

    task_id: int
    trial: int = 0
    success: bool = False
    reward: float = 0.0
    num_steps: int = 0
    context_mode: str = "baseline"
    context_items_retrieved: int = 0
    context_items_stored: int = 0
    feedback_applied: int = 0
    compact_report: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    token_usage: dict[str, int] = field(
        default_factory=lambda: {"prompt": 0, "completion": 0}
    )
    messages: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
