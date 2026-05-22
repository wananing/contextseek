"""Adapter wrapping the ContextSeek-enabled AppWorld ReAct agent."""

from __future__ import annotations

from typing import Any

from ..agent import AppWorldContextSeekAgent
from ..context import ContextSeekClient
from .base import AgentAdapter, RunResult, TrajectoryStep


def build_scope(config: dict[str, Any]) -> str:
    """Render the ContextSeek scope from config and experiment metadata."""
    seek_cfg = config.get("contextseek", {})
    template = seek_cfg.get("scope", "appworld/{experiment_name}/{dataset}/global")
    return template.format(
        experiment_name=config.get("experiment_name", "contextseek_eval"),
        dataset=config.get("dataset", "dev"),
        agent_type=config.get("type", "contextseek_react"),
    )


class ContextSeekReactAdapter(AgentAdapter):
    """Run AppWorld tasks with ContextSeek retrieval and trajectory writes."""

    @property
    def name(self) -> str:
        return "contextseek_react"

    def __init__(self) -> None:
        self._agent: AppWorldContextSeekAgent | None = None

    def configure(self, config: dict[str, Any]) -> None:
        seek_cfg = config.get("contextseek", {})
        contextseek_client = None
        if seek_cfg.get("enabled", True):
            contextseek_client = ContextSeekClient.from_config(
                seek_cfg,
                scope=build_scope(config),
            )

        self._agent = AppWorldContextSeekAgent(
            llm_model=config.get("model", "gpt-4o"),
            llm_api_key=config.get("llm_api_key"),
            llm_base_url=config.get("llm_base_url"),
            llm_provider=config.get("llm_provider"),
            azure_endpoint=config.get("azure_endpoint"),
            azure_api_version=config.get("azure_api_version"),
            azure_deployment=config.get("azure_deployment"),
            contextseek_client=contextseek_client,
            max_steps=config.get("max_steps", 25),
            temperature=config.get("temperature", 0.0),
            experiment_name=config.get("experiment_name", "contextseek_eval"),
            store_only=config.get("store_only", False),
            auto_compact=config.get("auto_compact", False),
            initial_context_tokens=config.get("initial_context_tokens", 1200),
            error_context_limit=config.get("error_context_limit", 3),
            appworld_python=config.get("appworld_python") or config.get("python"),
        )

    def run_task(self, task_id: str, **kwargs: Any) -> RunResult:
        if self._agent is None:
            raise RuntimeError("ContextSeekReactAdapter.configure() must be called first")
        raw = self._agent.run_task(task_id)
        return RunResult(
            task_id=raw.task_id,
            agent=self.name,
            success=raw.success,
            num_steps=raw.num_steps,
            duration_ms=raw.duration_ms,
            token_usage=raw.token_usage,
            steps=[
                TrajectoryStep(
                    thought=step.get("thought", ""),
                    code=step.get("code"),
                    observation=step.get("observation"),
                )
                for step in raw.trajectory
            ],
            metadata={
                "context_mode": raw.context_mode,
                "llm_model": self._agent.llm_model,
                "context_items_retrieved": raw.context_items_retrieved,
                "context_items_stored": raw.context_items_stored,
                "feedback_applied": raw.feedback_applied,
                "compact_report": raw.compact_report,
            },
            error=raw.error,
        )
