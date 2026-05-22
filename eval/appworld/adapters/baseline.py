"""Baseline adapter: same ReAct agent, no ContextSeek integration."""

from __future__ import annotations

from typing import Any

from ..agent import AppWorldContextSeekAgent
from .base import AgentAdapter, RunResult, TrajectoryStep


class BaselineAdapter(AgentAdapter):
    """Run AppWorld tasks without ContextSeek retrieval or writes."""

    @property
    def name(self) -> str:
        return "baseline"

    def __init__(self) -> None:
        self._agent: AppWorldContextSeekAgent | None = None

    def configure(self, config: dict[str, Any]) -> None:
        self._agent = AppWorldContextSeekAgent(
            llm_model=config.get("model", "gpt-4o"),
            llm_api_key=config.get("llm_api_key"),
            llm_base_url=config.get("llm_base_url"),
            llm_provider=config.get("llm_provider"),
            azure_endpoint=config.get("azure_endpoint"),
            azure_api_version=config.get("azure_api_version"),
            azure_deployment=config.get("azure_deployment"),
            contextseek_client=None,
            max_steps=config.get("max_steps", 25),
            temperature=config.get("temperature", 0.0),
            experiment_name=config.get("experiment_name", "contextseek_eval"),
            appworld_python=config.get("appworld_python") or config.get("python"),
        )

    def run_task(self, task_id: str, **kwargs: Any) -> RunResult:
        if self._agent is None:
            raise RuntimeError("BaselineAdapter.configure() must be called first")
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
            },
            error=raw.error,
        )
