"""AppWorld environment bridge.

The default path imports AppWorld in-process. When ``appworld_python`` is set,
the bridge launches ``appworld_worker.py`` with that interpreter so AppWorld can
live in a separate virtualenv from ContextSeek.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .appworld_worker import SENTINEL


def normalize_optional_str(value: str | None) -> str | None:
    """Return None for empty values or unresolved ``${VAR}`` YAML placeholders."""
    if not value:
        return None
    value = str(value).strip()
    if not value or value.startswith("${"):
        return None
    return value


def normalize_optional_path(value: str | None) -> str | None:
    """Return None for unset or unresolved env-substitution placeholders."""
    return normalize_optional_str(value)


class InProcessAppWorldSession:
    """In-process AppWorld session for environments where imports are compatible."""

    def __init__(self, *, task_id: str, experiment_name: str) -> None:
        self._task_id = task_id
        self._experiment_name = experiment_name
        self._cm = None
        self._world = None
        self.instruction = ""
        self.supervisor: dict[str, str] = {}

    def __enter__(self) -> "InProcessAppWorldSession":
        from appworld.environment import AppWorld

        self._cm = AppWorld(task_id=self._task_id, experiment_name=self._experiment_name)
        self._world = self._cm.__enter__()
        supervisor = self._world.task.supervisor
        self.instruction = self._world.task.instruction
        self.supervisor = {
            "first_name": supervisor.first_name,
            "last_name": supervisor.last_name,
            "email": supervisor.email,
            "phone_number": supervisor.phone_number,
        }
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._cm is not None:
            self._cm.__exit__(exc_type, exc, tb)

    def execute(self, code: str) -> str:
        if self._world is None:
            raise RuntimeError("AppWorld session is not started")
        return self._world.execute(code)

    def evaluate_success(self) -> bool:
        if self._world is None:
            raise RuntimeError("AppWorld session is not started")
        return bool(self._world.evaluate().success)


class SubprocessAppWorldSession:
    """Persistent AppWorld session backed by a worker subprocess."""

    def __init__(self, *, python: str, task_id: str, experiment_name: str) -> None:
        self._python = python
        self._task_id = task_id
        self._experiment_name = experiment_name
        self._proc: subprocess.Popen[str] | None = None
        self.instruction = ""
        self.supervisor: dict[str, str] = {}

    def __enter__(self) -> "SubprocessAppWorldSession":
        worker_path = Path(__file__).with_name("appworld_worker.py")
        self._proc = subprocess.Popen(
            [self._python, str(worker_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
            bufsize=1,
        )
        response = self._request(
            {
                "cmd": "start",
                "task_id": self._task_id,
                "experiment_name": self._experiment_name,
            }
        )
        self.instruction = response["instruction"]
        self.supervisor = dict(response["supervisor"])
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._proc is None:
            return
        try:
            self._request({"cmd": "close"})
        except Exception:
            self._proc.terminate()
        finally:
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None

    def execute(self, code: str) -> str:
        return str(self._request({"cmd": "execute", "code": code}).get("observation", ""))

    def evaluate_success(self) -> bool:
        return bool(self._request({"cmd": "evaluate"}).get("success", False))

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
            raise RuntimeError("AppWorld worker is not running")
        self._proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._proc.stdin.flush()

        while True:
            line = self._proc.stdout.readline()
            if line == "":
                raise RuntimeError("AppWorld worker exited before responding")
            if not line.startswith(SENTINEL):
                continue
            response = json.loads(line[len(SENTINEL):])
            if not response.get("ok"):
                detail = response.get("traceback") or response.get("error")
                raise RuntimeError(f"AppWorld worker error: {detail}")
            return response


def appworld_session(
    *,
    task_id: str,
    experiment_name: str,
    appworld_python: str | None = None,
) -> InProcessAppWorldSession | SubprocessAppWorldSession:
    """Create an AppWorld session, using a subprocess when configured."""
    normalized = normalize_optional_path(appworld_python)
    if normalized:
        return SubprocessAppWorldSession(
            python=normalized,
            task_id=task_id,
            experiment_name=experiment_name,
        )
    return InProcessAppWorldSession(task_id=task_id, experiment_name=experiment_name)
