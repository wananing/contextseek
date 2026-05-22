#!/usr/bin/env python3
"""CLI for the ContextSeek AppWorld evaluation pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from eval.appworld.adapters import get_adapter_class
from eval.appworld.environment import normalize_optional_path
from eval.appworld.pipeline import distill_stage, evaluate_stage, load_config, load_task_ids, run_stage


def _parse_stages(value: str) -> list[str]:
    stages = [stage.strip() for stage in value.split(",") if stage.strip()]
    valid = {"run", "distill", "evaluate"}
    unknown = sorted(set(stages) - valid)
    if unknown:
        raise ValueError(f"unknown stages: {', '.join(unknown)}")
    return stages


def _merged_agent_config(config: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    agent_cfg: dict[str, Any] = {**config.get("agent", {})}
    agent_cfg["experiment_name"] = config.get("experiment_name", "contextseek_eval")
    agent_cfg["dataset"] = config.get("dataset", "dev")
    agent_cfg["output_dir"] = str(base_dir)
    if "contextseek" in config:
        agent_cfg["contextseek"] = config["contextseek"]
    if "appworld" in config:
        agent_cfg.update(config["appworld"])
    return agent_cfg


def _appworld_python(config: dict[str, Any]) -> str | None:
    appworld_cfg = config.get("appworld", {})
    return normalize_optional_path(
        config.get("appworld_python")
        or appworld_cfg.get("python")
        or appworld_cfg.get("python_path")
    )


def run_pipeline(config: dict[str, Any], stages: list[str]) -> None:
    """Execute selected pipeline stages."""
    output_dir = Path(config.get("output_dir", "./output"))
    experiment_name = config.get("experiment_name", "contextseek_eval")
    base_dir = output_dir / experiment_name
    trajectories_dir = base_dir / "trajectories"
    evaluate_dir = base_dir / "evaluate"
    distill_dir = base_dir / "distill"

    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / "config_snapshot.json").write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    dataset = config.get("dataset", "dev")
    max_tasks = config.get("max_tasks")
    task_ids = load_task_ids(dataset, max_tasks, appworld_python=_appworld_python(config))
    print(f"Loaded {len(task_ids)} tasks from {dataset!r}")

    if "run" in stages:
        agent_cfg = _merged_agent_config(config, base_dir)
        adapter_name = agent_cfg.get("type", "contextseek_react")
        adapter = get_adapter_class(adapter_name)()
        adapter.configure(agent_cfg)
        print(f"\n=== Stage: run ({adapter.name}) ===")
        run_stage(
            adapter,
            task_ids,
            trajectories_dir / f"{adapter.name}.jsonl",
            resume=config.get("resume", True),
        )

    if "distill" in stages:
        print("\n=== Stage: distill ===")
        status = distill_stage(trajectories_dir, distill_dir, config)
        for name, message in status.items():
            print(f"  {name}: {message}")

    if "evaluate" in stages:
        print("\n=== Stage: evaluate ===")
        report_path = evaluate_stage(
            trajectories_dir,
            evaluate_dir,
            adapter_names=config.get("evaluate", {}).get("adapter_names"),
        )
        print(f"Report written to: {report_path}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=str(Path(__file__).resolve().parent / "config" / "default.yaml"),
        help="Path to an AppWorld evaluation YAML config.",
    )
    parser.add_argument(
        "--stage",
        default="run,evaluate",
        help="Comma-separated stages: run,distill,evaluate.",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Re-run every task even if its task_id already exists in the trajectory JSONL.",
    )
    args = parser.parse_args(argv)

    config = load_config(args.config)
    if args.no_resume:
        config = {**config, "resume": False}
    run_pipeline(config, _parse_stages(args.stage))


if __name__ == "__main__":
    main()
