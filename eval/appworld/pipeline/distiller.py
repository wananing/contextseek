"""Pipeline stage: distill reusable AppWorld knowledge into ContextSeek."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from contextseek import Stage

from ..adapters.contextseek_react import build_scope
from ..context import ContextSeekClient


_API_CALL_RE = re.compile(r"apis\.([a-zA-Z_][\w]*)\.([a-zA-Z_][\w]*)")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
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


def _extract_api_calls(steps: list[dict[str, Any]]) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []
    for step in steps:
        code = step.get("code") or ""
        for app, api in _API_CALL_RE.findall(code):
            if app in {"api_docs", "supervisor"}:
                continue
            calls.append((app, api))
    return list(dict.fromkeys(calls))


def _extract_relevant_code(steps: list[dict[str, Any]]) -> list[str]:
    snippets: list[str] = []
    for step in steps:
        code = step.get("code") or ""
        lines = [
            line
            for line in code.splitlines()
            if "apis." in line or "page_index" in line or "page_limit" in line
        ]
        if lines:
            snippets.append(_truncate("\n".join(lines), 500))
    return snippets[:3]


def _heuristic_experiences(record: dict[str, Any]) -> list[dict[str, Any]]:
    steps = record.get("steps", [])
    success = bool(record.get("success"))
    calls = _extract_api_calls(steps)
    snippets = _extract_relevant_code(steps)
    task_id = record.get("task_id", "unknown")

    if success and calls:
        apps = ", ".join(sorted({app for app, _ in calls}))
        apis = ", ".join(f"{app}.{api}" for app, api in calls[:8])
        content = (
            f"Successful AppWorld task `{task_id}` used apps: {apps}.\n"
            f"Useful API calls: {apis}.\n"
            "Reusable code/API patterns:\n"
            + "\n\n".join(snippets)
        )
        return [
            {
                "title": f"Successful API pattern from {task_id}",
                "content": content,
                "tags": sorted({app for app, _ in calls}) + ["api_pattern", "success"],
                "stage": "knowledge",
                "confidence": 0.72,
            }
        ]

    error_observations = [
        step.get("observation", "")
        for step in steps
        if step.get("observation") and _looks_like_error(step.get("observation", ""))
    ]
    if error_observations:
        content = (
            f"Failed AppWorld task `{task_id}` produced an error that may recur.\n"
            f"Error observation:\n{_truncate(error_observations[-1], 900)}"
        )
        return [
            {
                "title": f"Failure note from {task_id}",
                "content": content,
                "tags": ["failure", "error_recovery"],
                "stage": "extracted",
                "confidence": 0.55,
            }
        ]
    return []


def _looks_like_error(text: str) -> bool:
    indicators = ("Traceback", "Exception:", "Error:", "Execution failed", "ValidationError")
    return any(indicator in text for indicator in indicators)


def distill_stage(
    trajectories_dir: Path,
    output_dir: Path,
    config: dict[str, Any],
) -> dict[str, str]:
    """Distill trajectory JSONL into ContextSeek knowledge items."""
    output_dir.mkdir(parents=True, exist_ok=True)
    seek_cfg = config.get("contextseek", {})
    if not seek_cfg.get("enabled", True):
        message = "skipped (contextseek.enabled=false)"
        (output_dir / "distill.log").write_text(message + "\n", encoding="utf-8")
        return {"contextseek": message}

    scope = build_scope(
        {
            **config.get("agent", {}),
            "contextseek": seek_cfg,
            "experiment_name": config.get("experiment_name", "contextseek_eval"),
            "dataset": config.get("dataset", "dev"),
        }
    )
    contextseek = ContextSeekClient.from_config(seek_cfg, scope=scope)
    max_records = config.get("distill", {}).get("max_records")
    compact_after = config.get("distill", {}).get("compact_after", True)

    status: dict[str, str] = {}
    total_stored = 0
    for path in sorted(trajectories_dir.glob("*.jsonl")):
        records = _load_jsonl(path)
        if max_records:
            records = records[: int(max_records)]
        stored = 0
        for record in records:
            for exp in _heuristic_experiences(record):
                stage = Stage(exp.get("stage", "knowledge"))
                contextseek.store_experience(
                    title=exp["title"],
                    content=exp["content"],
                    source=f"appworld_distill:{record.get('task_id', 'unknown')}",
                    tags=exp.get("tags", []),
                    stage=stage,
                    confidence=float(exp.get("confidence", 0.7)),
                )
                stored += 1
        total_stored += stored
        status[path.stem] = f"stored {stored} distilled items"

    compact_report = contextseek.compact() if compact_after else {}
    log_lines = [f"{name}: {message}" for name, message in status.items()]
    log_lines.append(f"total_stored: {total_stored}")
    if compact_report:
        log_lines.append(f"compact: {json.dumps(compact_report, ensure_ascii=False)}")
    (output_dir / "distill.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    return status
