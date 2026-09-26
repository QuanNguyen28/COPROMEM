"""Run the unchanged official ReMe AppWorld agent over the JSON-lines worker."""
from __future__ import annotations

import contextvars
import importlib
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import types
from typing import Any

from research.official_pilot.locked_openrouter import AppendOnlyLedger, LockedOpenAI

ROOT = pathlib.Path("/mnt/e/Project/AAMAS/COPROMEM")
SOURCE = pathlib.Path("/home/xiqhq/copromem-reme")
NATIVE_PYTHON = "/home/xiqhq/copromem-appworld/venv/bin/python"
NATIVE_ROOT = "/home/xiqhq/copromem-appworld"
WORKER = ROOT / "research/containers/appworld/official_reme_worker.py"
CALL_ROLE: contextvars.ContextVar[str] = contextvars.ContextVar("call_role", default="executor")


def safe_journal_path(parent: pathlib.Path, trajectory_id: str) -> pathlib.Path:
    """Derive an E-drive/WSL-safe journal name without changing provenance."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", trajectory_id).strip("_")
    if not safe:
        raise ValueError("empty trajectory ID is not journal-safe")
    return parent / f"{safe}.jsonl"


class AppWorldProxy:
    allowed_tasks: str = ""
    journal_path: pathlib.Path | None = None
    journal_trajectory_id: str = ""
    def __init__(self, task_id: str, experiment_name: str, **_: Any) -> None:
        self._proc = subprocess.Popen([NATIVE_PYTHON, str(WORKER)], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, text=True, cwd=NATIVE_ROOT,
            env={**__import__("os").environ, "APPWORLD_ALLOWED_TASKS": self.allowed_tasks})
        self.task_id = task_id
        start = self._send({"op": "start", "task_id": task_id, "experiment_name": experiment_name})
        self.task = types.SimpleNamespace(instruction=start["instruction"], supervisor=start["supervisor"],
            app_descriptions=start["app_descriptions"])
        self._completed = False
        self._finished = False
        self._action_index = 0

    def _send(self, value: dict[str, Any]) -> dict[str, Any]:
        assert self._proc.stdin and self._proc.stdout
        import json
        self._proc.stdin.write(json.dumps(value) + "\n"); self._proc.stdin.flush()
        response = json.loads(self._proc.stdout.readline())
        if not response.get("ok"):
            raise RuntimeError("native AppWorld worker rejected request")
        return response

    def __enter__(self) -> "AppWorldProxy": return self
    def __exit__(self, *_: Any) -> None:
        if not self._finished and self._proc.poll() is None:
            self._send({"op": "finish"}); self._finished = True
        if self._proc.poll() is None: self._proc.wait(timeout=20)

    def execute(self, code: str) -> str:
        # Durably journal the submitted native action before asking the worker
        # to apply it.  The journal deliberately stores only a digest of the
        # code: the task transcript remains in the per-trajectory artifact.
        if self.journal_path is not None:
            import hashlib
            record = {"event": "action_submitted", "task_id": self.task_id,
                      "trajectory_id": self.journal_trajectory_id,
                      "index": self._action_index,
                      # Required for restart recovery.  This is a public
                      # agent action, never hidden checker/task state.
                      "code": code,
                      "code_sha256": hashlib.sha256(code.encode("utf-8")).hexdigest(),
                      "time_ns": time.time_ns()}
            self.journal_path.parent.mkdir(parents=True, exist_ok=True)
            with self.journal_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
                handle.flush(); os.fsync(handle.fileno())
        response = self._send({"op": "action", "code": code})
        self._completed = bool(response["completed"])
        if self.journal_path is not None:
            record = {"event": "action_applied", "task_id": self.task_id,
                      "trajectory_id": self.journal_trajectory_id,
                      "index": self._action_index, "completed": self._completed,
                      "output_sha256": __import__("hashlib").sha256(
                          str(response["output"]).encode("utf-8")).hexdigest(),
                      "time_ns": time.time_ns()}
            self.journal_path.parent.mkdir(parents=True, exist_ok=True)
            with self.journal_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
                handle.flush(); os.fsync(handle.fileno())
        self._action_index += 1
        return response["output"]

    def task_completed(self) -> bool: return self._completed
    def evaluate(self) -> Any:
        response = self._send({"op": "score"})
        if self.journal_path is not None:
            record = {"event": "official_score", "task_id": self.task_id,
                      "trajectory_id": self.journal_trajectory_id,
                      "pass_count": int(response["pass_count"]),
                      "fail_count": int(response["fail_count"]), "time_ns": time.time_ns()}
            self.journal_path.parent.mkdir(parents=True, exist_ok=True)
            with self.journal_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
                handle.flush(); os.fsync(handle.fileno())
        return types.SimpleNamespace(passes=[None] * int(response["pass_count"]),
            failures=[None] * int(response["fail_count"]))


def load_official_agent(*, allowed_tasks: list[str], api_key: str, ledger: AppendOnlyLedger,
                        progress: pathlib.Path, journal_path: pathlib.Path | None = None,
                        trajectory_id: str = "") -> type:
    AppWorldProxy.allowed_tasks = ",".join(allowed_tasks)
    AppWorldProxy.journal_path = journal_path
    AppWorldProxy.journal_trajectory_id = trajectory_id
    stub = types.ModuleType("appworld")
    stub.AppWorld = AppWorldProxy
    stub.load_task_ids = lambda _: list(allowed_tasks)
    sys.modules["appworld"] = stub
    appworld_path = str(SOURCE / "benchmark/appworld")
    if appworld_path not in sys.path: sys.path.insert(0, appworld_path)
    module = importlib.import_module("appworld_react_agent")
    module.OpenAI = lambda: LockedOpenAI(api_key=api_key, ledger=ledger, progress=progress,
        role=CALL_ROLE.get())
    cls = module.AppworldReactAgent.__ray_metadata__.modified_class
    source = pathlib.Path(__import__("inspect").getsourcefile(cls)).resolve()
    if SOURCE not in source.parents or any(name.endswith("reme_paper_lifecycle") for name in sys.modules):
        raise RuntimeError("official upstream executor integrity violation")
    return cls
