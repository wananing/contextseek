"""Baseline adapter — native tau-bench agent without ContextSeek."""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass
from typing import Any

from eval.taubench import tau2_compat  # noqa: F401  # Python 3.13 compat
from eval.taubench.adapters.base import TaskResult


def _is_successful(reward: float) -> bool:
    return (1 - 1e-6) <= reward <= (1 + 1e-6)


def _message_get(message: Any, key: str, default: Any = None) -> Any:
    if isinstance(message, dict):
        return message.get(key, default)
    return getattr(message, key, default)


def _tool_call_get(tool_call: Any, key: str, default: Any = None) -> Any:
    if isinstance(tool_call, dict):
        return tool_call.get(key, default)
    return getattr(tool_call, key, default)


def _extract_tool_calls(messages: list[Any]) -> list[dict[str, Any]]:
    tool_calls: list[dict[str, Any]] = []
    for msg in messages:
        if _message_get(msg, "role") == "assistant" and _message_get(msg, "tool_calls"):
            for tc in _message_get(msg, "tool_calls", []):
                function = _tool_call_get(tc, "function", {}) or {}
                tool_calls.append({
                    "name": _tool_call_get(
                        tc,
                        "name",
                        _tool_call_get(function, "name", "unknown"),
                    ),
                    "arguments": _tool_call_get(
                        tc,
                        "arguments",
                        _tool_call_get(function, "arguments", ""),
                    ),
                })
    return tool_calls


def _count_agent_turns(messages: list[Any]) -> int:
    return sum(1 for msg in messages if _message_get(msg, "role") == "assistant")


@dataclass
class BaselineAdapter:
    """Runs tau-bench tasks with the native agent, no ContextSeek integration.

    Uses tau2's standard TextRunConfig → build_orchestrator → run_simulation pipeline.
    """

    domain: str = "airline"
    llm_agent: str = "gpt-4o"
    llm_args_agent: dict | None = None
    agent: str = "llm_agent"
    user: str = "user_simulator"
    llm_user: str = "gpt-4o"
    llm_args_user: dict | None = None
    max_steps: int = 100
    max_errors: int = 10
    seed: int = 42

    @property
    def adapter_name(self) -> str:
        return "baseline"

    def run_task(self, task_id: int, trial: int = 0) -> TaskResult:
        result = TaskResult(
            task_id=task_id,
            trial=trial,
            context_mode="baseline",
        )
        started_at = time.time()

        try:
            from tau2.data_model.simulation import TextRunConfig
            from tau2.runner import build_orchestrator, get_tasks, run_simulation

            tasks = get_tasks(self.domain)
            if task_id < 0 or task_id >= len(tasks):
                result.error = (
                    f"task_id {task_id} out of range [0, {len(tasks)})"
                )
                result.duration_ms = int((time.time() - started_at) * 1000)
                return result

            task = tasks[task_id]
            sim_seed = self.seed + task_id + trial
            config = TextRunConfig(
                domain=self.domain,
                agent=self.agent,
                user=self.user,
                llm_agent=self.llm_agent,
                llm_args_agent=self.llm_args_agent or {},
                llm_user=self.llm_user,
                llm_args_user=self.llm_args_user or {},
                max_steps=self.max_steps,
                max_errors=self.max_errors,
                seed=sim_seed,
            )

            orch = build_orchestrator(config, task, seed=sim_seed)
            sim_run = run_simulation(orch)

            reward = sim_run.reward_info.reward if sim_run.reward_info else 0.0
            result.reward = reward
            result.success = _is_successful(reward)
            result.messages = sim_run.messages or []
            result.tool_calls = _extract_tool_calls(result.messages)
            result.num_steps = _count_agent_turns(result.messages)

        except Exception as exc:
            result.error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"

        result.duration_ms = int((time.time() - started_at) * 1000)
        return result
