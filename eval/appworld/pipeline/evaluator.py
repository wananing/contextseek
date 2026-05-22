"""Pipeline stage: aggregate AppWorld trajectory JSONL into reports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _load_results(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    results: list[dict[str, Any]] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                results.append(json.loads(line))
    return results


def _fmt_tokens(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def _read_default_llm_from_config(experiment_dir: Path) -> str | None:
    snap = experiment_dir / "config_snapshot.json"
    if not snap.exists():
        return None
    try:
        cfg = json.loads(snap.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    model = (cfg.get("agent") or {}).get("model")
    return str(model) if model else None


def _llm_label(results: list[dict[str, Any]], *, default_llm: str | None) -> str:
    models: list[str] = []
    for result in results:
        meta = result.get("metadata") or {}
        m = meta.get("llm_model")
        if m:
            models.append(str(m))
    unique = sorted(set(models))
    if len(unique) == 1:
        return unique[0]
    if len(unique) > 1:
        return ", ".join(unique)
    return default_llm or "-"


def _stats(
    results: list[dict[str, Any]],
    *,
    default_llm: str | None,
) -> dict[str, Any]:
    total = len(results)
    if total == 0:
        return {
            "n": 0,
            "success": 0,
            "rate": 0.0,
            "avg_steps": 0.0,
            "total_prompt": 0,
            "total_completion": 0,
            "context_items_retrieved": 0,
            "context_items_stored": 0,
            "feedback_applied": 0,
            "llm": default_llm or "-",
            "total_time_s": 0.0,
            "avg_time_s": 0.0,
        }

    successes = sum(1 for result in results if result.get("success"))
    metadata = [result.get("metadata", {}) for result in results]
    total_prompt = sum(result.get("token_usage", {}).get("prompt", 0) for result in results)
    total_completion = sum(
        result.get("token_usage", {}).get("completion", 0) for result in results
    )
    total_duration_ms = sum(int(result.get("duration_ms") or 0) for result in results)
    total_time_s = total_duration_ms / 1000.0
    return {
        "n": total,
        "success": successes,
        "rate": successes / total * 100,
        "avg_steps": round(sum(result.get("num_steps", 0) for result in results) / total, 1),
        "total_prompt": total_prompt,
        "total_completion": total_completion,
        "context_items_retrieved": sum(
            item.get("context_items_retrieved", 0) for item in metadata
        ),
        "context_items_stored": sum(item.get("context_items_stored", 0) for item in metadata),
        "feedback_applied": sum(item.get("feedback_applied", 0) for item in metadata),
        "llm": _llm_label(results, default_llm=default_llm),
        "total_time_s": round(total_time_s, 1),
        "avg_time_s": round(total_time_s / total, 1),
    }


def _build_report_section(
    all_data: dict[str, list[dict[str, Any]]],
    all_stats: dict[str, dict[str, Any]],
    *,
    run_title: str,
) -> list[str]:
    lines = [
        f"## {run_title}",
        "",
        "| Agent | LLM | Tasks | Pass | Rate | Avg Steps | Time | Avg Time | Tokens | Retrieved | Stored | Feedback |",
        "|-------|-----|-------|------|------|-----------|------|----------|--------|-----------|--------|----------|",
    ]
    for name, stats in all_stats.items():
        tokens = stats["total_prompt"] + stats["total_completion"]
        lines.append(
            f"| {name} | {stats['llm']} | {stats['n']} | {stats['success']} | {stats['rate']:.1f}% "
            f"| {stats['avg_steps']} | {stats['total_time_s']:.1f}s | {stats['avg_time_s']:.1f}s "
            f"| {_fmt_tokens(tokens)} "
            f"| {stats['context_items_retrieved']} | {stats['context_items_stored']} "
            f"| {stats['feedback_applied']} |"
        )
    lines.append("")

    if len(all_data) > 1:
        task_ids = list(
            dict.fromkeys(
                task_id
                for results in all_data.values()
                for task_id in (result["task_id"] for result in results)
            )
        )
        header = "| Task ID | " + " | ".join(all_data.keys()) + " |"
        sep = "|---------|" + "|".join("---" for _ in all_data) + "|"
        lines += ["### Per-Task Comparison", "", header, sep]
        for task_id in task_ids:
            cells: list[str] = []
            for name in all_data:
                match = next(
                    (result for result in all_data[name] if result["task_id"] == task_id),
                    None,
                )
                cells.append("-" if match is None else ("pass" if match.get("success") else "fail"))
            lines.append(f"| {task_id} | " + " | ".join(cells) + " |")
        lines.append("")

    return lines


def evaluate_stage(
    trajectories_dir: Path,
    output_dir: Path,
    *,
    adapter_names: list[str] | None = None,
) -> str:
    """Generate ``report.md`` (append) and ``summary.json`` from trajectory files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    experiment_dir = output_dir.parent
    default_llm = _read_default_llm_from_config(experiment_dir)

    if adapter_names:
        trajectory_files = [(name, trajectories_dir / f"{name}.jsonl") for name in adapter_names]
    else:
        trajectory_files = sorted((path.stem, path) for path in trajectories_dir.glob("*.jsonl"))

    all_data: dict[str, list[dict[str, Any]]] = {}
    all_stats: dict[str, dict[str, Any]] = {}
    for name, path in trajectory_files:
        results = _load_results(path)
        all_data[name] = results
        all_stats[name] = _stats(results, default_llm=default_llm)

    run_title = f"Evaluation run ({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC)"
    section_lines = _build_report_section(all_data, all_stats, run_title=run_title)

    report_path = output_dir / "report.md"
    if report_path.exists():
        existing = report_path.read_text(encoding="utf-8").rstrip("\n")
        report_path.write_text(existing + "\n\n" + "\n".join(section_lines) + "\n", encoding="utf-8")
    else:
        header = ["# AppWorld ContextSeek Evaluation Report", ""]
        report_path.write_text("\n".join(header + section_lines) + "\n", encoding="utf-8")

    (output_dir / "summary.json").write_text(
        json.dumps(all_stats, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return str(report_path)
