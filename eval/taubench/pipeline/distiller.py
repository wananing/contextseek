"""Pipeline stage: distill tau-bench trajectories into ContextSeek knowledge.

Tau-bench specific distillation strategies:
1. Successful trajectory → API call sequence patterns (stage=knowledge)
2. Failed trajectory → Policy violation notes (stage=extracted)
3. Same user_id across tasks → User preference inference (stage=knowledge)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from contextseek import Stage

from eval.taubench.context import TauBenchContextSeekClient


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    if not path.exists():
        return records
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _truncate(text: str, limit: int = 700) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n... (truncated)"


def _looks_like_error(text: str) -> bool:
    indicators = (
        "Error:", "Traceback", "Exception:", "invalid",
        "not allowed", "cannot", "policy", "violation",
    )
    return any(indicator.lower() in text.lower() for indicator in indicators)


def distill_stage(
    trajectories_dir: Path,
    output_dir: Path,
    contextseek_client: TauBenchContextSeekClient,
    *,
    compact_after: bool = True,
    max_records: int | None = None,
) -> dict[str, str]:
    """Distill trajectory JSONL files into ContextSeek knowledge items.

    Args:
        trajectories_dir: Directory containing *.jsonl trajectory files.
        output_dir: Directory to write distill.log.
        contextseek_client: Configured ContextSeek client.
        compact_after: Whether to run compact() after distillation.
        max_records: Max records to process per file.

    Returns:
        Status dict mapping filename → result message.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    status: dict[str, str] = {}
    total_stored = 0

    for path in sorted(trajectories_dir.glob("*.jsonl")):
        records = _load_jsonl(path)
        if max_records:
            records = records[:max_records]
        stored = 0

        for record in records:
            experiences = _heuristic_experiences(record, contextseek_client.domain)
            for exp in experiences:
                stage = Stage(exp.get("stage", "knowledge"))
                contextseek_client.store_experience(
                    title=exp["title"],
                    content=exp["content"],
                    source=f"taubench_distill:{record.get('task_id', 'unknown')}",
                    tags=exp.get("tags", []),
                    stage=stage,
                    confidence=float(exp.get("confidence", 0.7)),
                )
                stored += 1

        total_stored += stored
        status[path.stem] = f"stored {stored} distilled items"

    compact_report = {}
    if compact_after:
        compact_report = contextseek_client.compact()

    log_lines = [f"{name}: {message}" for name, message in status.items()]
    log_lines.append(f"total_stored: {total_stored}")
    if compact_report:
        log_lines.append(f"compact: {json.dumps(compact_report, ensure_ascii=False)}")
    (output_dir / "distill.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    return status


def _heuristic_experiences(record: dict[str, Any], domain: str) -> list[dict[str, Any]]:
    """Extract reusable knowledge from a tau-bench trajectory record.

    The record may be a flat TaskResult dict (from runner) or a richer
    trajectory containing tool_calls / messages / policy_checks fields.
    """
    task_id = record.get("task_id", "unknown")
    success = bool(record.get("success"))
    experiences: list[dict[str, Any]] = []

    # ── Pattern 1: Successful trajectory → API call sequence ──
    tool_calls = record.get("tool_calls", [])
    if success and tool_calls:
        api_sequence = [tc.get("name", "?") for tc in tool_calls[:10]]
        unique_apis = list(dict.fromkeys(api_sequence))
        content = (
            f"Successful {domain} task `{task_id}` used these tool calls:\n"
            + " → ".join(unique_apis)
            + "\n\nThis sequence may be reusable for similar tasks."
        )
        experiences.append({
            "title": f"Successful {domain} pattern (task {task_id})",
            "content": content,
            "tags": [domain, "api_pattern", "success"],
            "stage": "knowledge",
            "confidence": 0.72,
        })

    # ── Pattern 2: Failed trajectory → Policy violation note ──
    if not success:
        error_msg = record.get("error", "")
        # If we have the full messages, look for tool errors
        messages = record.get("messages", [])
        tool_errors = [
            m.get("content", "")
            for m in messages
            if m.get("role") == "tool" and _looks_like_error(m.get("content", ""))
        ]
        if tool_errors or error_msg:
            error_text = tool_errors[-1] if tool_errors else error_msg
            content = (
                f"Failed {domain} task `{task_id}`.\n"
                f"Error encountered: {_truncate(error_text, 900)}\n\n"
                "Consider this when handling similar requests in the future."
            )
            experiences.append({
                "title": f"Failure note from {domain} task {task_id}",
                "content": content,
                "tags": [domain, "failure", "error_recovery"],
                "stage": "extracted",
                "confidence": 0.55,
            })

    return experiences
