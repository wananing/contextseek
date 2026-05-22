"""ReAct AppWorld agent with optional ContextSeek integration."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from .context import ContextSeekClient
from .environment import appworld_session, normalize_optional_path, normalize_optional_str
from .llm import LLMClient, detect_provider
from .prompts import CONTEXT_ADDON, FEWSHOT_DEMO, REACT_STEP_PROMPT, SYSTEM_PROMPT


@dataclass
class TaskResult:
    """Result of one AppWorld task run."""

    task_id: str
    success: bool
    num_steps: int
    context_mode: str
    context_items_retrieved: int = 0
    context_items_stored: int = 0
    feedback_applied: int = 0
    compact_report: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    token_usage: dict[str, int] = field(default_factory=lambda: {"prompt": 0, "completion": 0})
    trajectory: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


_CODE_BLOCK_RE = re.compile(r"```python\s*\n(.*?)```", re.DOTALL)
_STATUS_RE = re.compile(r"Status:\s*(completed|failed)", re.IGNORECASE)
_THOUGHT_RE = re.compile(r"Thought:\s*(.*?)(?=\nCode:|\nStatus:|\Z)", re.DOTALL)


def _parse_response(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {"thought": "", "code": None, "status": None}
    thought_match = _THOUGHT_RE.search(text)
    if thought_match:
        result["thought"] = thought_match.group(1).strip()

    status_match = _STATUS_RE.search(text)
    if status_match:
        result["status"] = status_match.group(1).lower()
        return result

    code_match = _CODE_BLOCK_RE.search(text)
    if code_match:
        result["code"] = code_match.group(1).strip()
    return result


def _looks_like_error(text: str) -> bool:
    indicators = ("Traceback", "Exception:", "Error:", "Execution failed", "ValidationError")
    return any(indicator in text for indicator in indicators)


class AppWorldContextSeekAgent:
    """Autonomous ReAct agent that can read/write ContextSeek between tasks."""

    def __init__(
        self,
        *,
        llm_model: str = "gpt-4o",
        llm_api_key: str | None = None,
        llm_base_url: str | None = None,
        llm_provider: str | None = None,
        azure_endpoint: str | None = None,
        azure_api_version: str | None = None,
        azure_deployment: str | None = None,
        contextseek_client: ContextSeekClient | None = None,
        max_steps: int = 25,
        temperature: float = 0.0,
        experiment_name: str = "contextseek_eval",
        store_only: bool = False,
        auto_compact: bool = False,
        initial_context_tokens: int = 1200,
        error_context_limit: int = 3,
        appworld_python: str | None = None,
    ) -> None:
        llm_api_key = normalize_optional_str(llm_api_key)
        llm_base_url = normalize_optional_str(llm_base_url)
        azure_endpoint = normalize_optional_str(azure_endpoint)
        azure_api_version = normalize_optional_str(azure_api_version)
        azure_deployment = normalize_optional_str(azure_deployment)
        llm_provider = normalize_optional_str(llm_provider)

        provider = detect_provider(
            llm_provider=llm_provider,
            llm_base_url=llm_base_url,
            azure_endpoint=azure_endpoint,
        )
        self.llm_model = azure_deployment if provider == "azure" and azure_deployment else llm_model
        self.llm = LLMClient(
            provider=provider,
            api_key=llm_api_key,
            base_url=llm_base_url,
            azure_endpoint=azure_endpoint or "",
            azure_api_version=azure_api_version,
        )
        self.contextseek = contextseek_client
        self.max_steps = max_steps
        self.temperature = temperature
        self.experiment_name = experiment_name
        self.store_only = store_only
        self.auto_compact = auto_compact
        self.initial_context_tokens = initial_context_tokens
        self.error_context_limit = error_context_limit
        self.appworld_python = normalize_optional_path(appworld_python)

    def run_task(self, task_id: str) -> TaskResult:
        """Run a single AppWorld task."""
        if self.store_only and self.contextseek:
            context_mode = "store_only"
        elif self.contextseek:
            context_mode = "contextseek"
        else:
            context_mode = "baseline"
        result = TaskResult(task_id=task_id, success=False, num_steps=0, context_mode=context_mode)
        retrieved_item_ids: list[str] = []
        started_at = time.time()

        try:
            with appworld_session(
                task_id=task_id,
                experiment_name=self.experiment_name,
                appworld_python=self.appworld_python,
            ) as world:
                instruction = world.instruction
                context_background = ""
                if self.contextseek and not self.store_only:
                    payload = self.contextseek.retrieve_for_task(
                        instruction,
                        max_tokens=self.initial_context_tokens,
                    )
                    context_background = payload.text
                    retrieved_item_ids.extend(payload.item_ids)
                    result.context_items_retrieved += payload.count

                messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
                user_info = dict(world.supervisor)
                for demo_msg in FEWSHOT_DEMO:
                    messages.append(
                        {
                            "role": demo_msg["role"],
                            "content": demo_msg["content"].format(**user_info),
                        }
                    )

                steps: list[dict[str, Any]] = []
                total_prompt = 0
                total_completion = 0
                consecutive_empty = 0

                for step_index in range(self.max_steps):
                    if step_index == 0:
                        context_section = (
                            CONTEXT_ADDON.format(context_background=context_background)
                            if context_background
                            else ""
                        )
                        user_msg = REACT_STEP_PROMPT.format(
                            instruction=instruction,
                            context_section=context_section,
                            **user_info,
                        )
                    else:
                        previous = steps[-1]
                        observation = previous.get("observation")
                        if observation:
                            user_msg = f"Observation:\n{observation}\n\nContinue with your next step."
                        else:
                            user_msg = (
                                "Your previous response did not contain executable code. "
                                "Please provide Thought + Code, or Thought + Status."
                            )
                    messages.append({"role": "user", "content": user_msg})

                    text, prompt_tokens, completion_tokens = self.llm.chat(
                        model=self.llm_model,
                        messages=messages,
                        temperature=self.temperature,
                    )
                    total_prompt += prompt_tokens
                    total_completion += completion_tokens
                    messages.append({"role": "assistant", "content": text})

                    parsed = _parse_response(text)
                    step_record: dict[str, Any] = {
                        "thought": parsed["thought"],
                        "code": parsed.get("code"),
                        "observation": None,
                    }

                    if parsed["status"]:
                        steps.append(step_record)
                        break

                    if parsed["code"]:
                        consecutive_empty = 0
                        observation = world.execute(parsed["code"])
                        if (
                            self.contextseek
                            and not self.store_only
                            and observation
                            and _looks_like_error(observation)
                        ):
                            payload = self.contextseek.retrieve_for_error(
                                observation,
                                limit=self.error_context_limit,
                            )
                            if payload.text:
                                observation = (
                                    f"{observation}\n\n"
                                    "Additional ContextSeek background for this error:\n"
                                    f"{payload.text}"
                                )
                            retrieved_item_ids.extend(payload.item_ids)
                            result.context_items_retrieved += payload.count
                        step_record["observation"] = observation
                    else:
                        consecutive_empty += 1
                        if consecutive_empty >= 3:
                            step_record["observation"] = (
                                "SYSTEM: You have not produced code for 3 consecutive steps. "
                                "Write executable Code or set Status."
                            )

                    steps.append(step_record)

                result.success = world.evaluate_success()
                result.num_steps = len(steps)
                result.trajectory = steps
                result.token_usage = {"prompt": total_prompt, "completion": total_completion}

                if self.contextseek:
                    self.contextseek.store_trajectory(
                        task_id=task_id,
                        instruction=instruction,
                        steps=steps,
                        success=result.success,
                    )
                    result.context_items_stored += 1
                    if result.success and retrieved_item_ids:
                        result.feedback_applied = self.contextseek.apply_success_feedback(retrieved_item_ids)
                    if self.auto_compact:
                        result.compact_report = self.contextseek.compact()

        except Exception as exc:
            result.error = str(exc)

        result.duration_ms = int((time.time() - started_at) * 1000)
        return result
