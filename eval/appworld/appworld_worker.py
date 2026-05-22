#!/usr/bin/env python3
"""JSONL worker that runs inside the AppWorld Python environment.

This file intentionally imports no ContextSeek modules. It is launched by the
ContextSeek evaluation process with the Python interpreter that has AppWorld
installed, then receives commands over stdin and writes sentinel-prefixed JSON
responses to stdout.
"""

from __future__ import annotations

import json
import sys
import traceback
from typing import Any


SENTINEL = "__APPWORLD_BRIDGE__"


def _respond(payload: dict[str, Any]) -> None:
    sys.stdout.write(SENTINEL + json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _supervisor_info(world: Any) -> dict[str, str]:
    supervisor = world.task.supervisor
    return {
        "first_name": str(getattr(supervisor, "first_name", "")),
        "last_name": str(getattr(supervisor, "last_name", "")),
        "email": str(getattr(supervisor, "email", "")),
        "phone_number": str(getattr(supervisor, "phone_number", "")),
    }


def main() -> None:
    world_cm = None
    world = None

    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            request = json.loads(raw_line)
            cmd = request.get("cmd")

            if cmd == "start":
                if world_cm is not None:
                    world_cm.__exit__(None, None, None)
                from appworld.environment import AppWorld

                world_cm = AppWorld(
                    task_id=request["task_id"],
                    experiment_name=request.get("experiment_name", "contextseek_eval"),
                )
                world = world_cm.__enter__()
                _respond(
                    {
                        "ok": True,
                        "instruction": world.task.instruction,
                        "supervisor": _supervisor_info(world),
                    }
                )
                continue

            if cmd == "execute":
                if world is None:
                    raise RuntimeError("AppWorld task has not been started")
                _respond({"ok": True, "observation": world.execute(request.get("code", ""))})
                continue

            if cmd == "evaluate":
                if world is None:
                    raise RuntimeError("AppWorld task has not been started")
                tracker = world.evaluate()
                _respond({"ok": True, "success": bool(tracker.success)})
                continue

            if cmd == "close":
                if world_cm is not None:
                    world_cm.__exit__(None, None, None)
                    world_cm = None
                    world = None
                _respond({"ok": True})
                break

            raise ValueError(f"unknown command: {cmd!r}")
        except Exception as exc:
            _respond(
                {
                    "ok": False,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )

    if world_cm is not None:
        world_cm.__exit__(None, None, None)


if __name__ == "__main__":
    main()
