#!/usr/bin/env python3
"""Zero-model fixture proving the official agent imports across the worker boundary."""
from __future__ import annotations

import importlib
import inspect
import json
import os
import pathlib
import subprocess
import sys
import types

ROOT = pathlib.Path("/mnt/e/Project/AAMAS/COPROMEM")
SOURCE = pathlib.Path("/home/xiqhq/copromem-reme").resolve()
NATIVE_PYTHON = "/home/xiqhq/copromem-appworld/venv/bin/python"
NATIVE_ROOT = "/home/xiqhq/copromem-appworld"
WORKER = ROOT / "research/containers/appworld/official_reme_worker.py"


class RemoteWorld:
    def __init__(self, task_id: str, experiment_name: str, **_: object) -> None:
        self._proc = subprocess.Popen(
            [NATIVE_PYTHON, str(WORKER)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
            env={**os.environ, "APPWORLD_ALLOWED_TASKS": "82e2fac_1"},
            cwd=NATIVE_ROOT,
        )
        self.task_id = task_id
        started = self._send({"op": "start", "task_id": task_id,
                              "experiment_name": experiment_name, "fixture": True})
        self.task = types.SimpleNamespace(
            instruction=started["instruction"], supervisor=started["supervisor"],
            app_descriptions=started["app_descriptions"],
        )

    def _send(self, payload: dict) -> dict:
        assert self._proc.stdin is not None and self._proc.stdout is not None
        self._proc.stdin.write(json.dumps(payload) + "\n")
        self._proc.stdin.flush()
        result = json.loads(self._proc.stdout.readline())
        if not result.get("ok"):
            raise RuntimeError(
                "native worker rejected public boundary request: "
                + result.get("error_type", "unknown")
                + ": " + result.get("error", "")
            )
        return result

    def __enter__(self) -> "RemoteWorld":
        return self

    def __exit__(self, *_: object) -> None:
        if self._proc.poll() is None:
            self._proc.terminate()
            self._proc.wait(timeout=10)

    def execute(self, code: str) -> str:
        return self._send({"op": "action", "code": code})["output"]

    def task_completed(self) -> bool:
        return self._send({"op": "score"})["success"]

    def finish_fixture(self) -> dict:
        result = self._send({"op": "finish", "fixture_solution": True})
        self._proc.wait(timeout=20)
        return result


# Substitute only the environment interface before importing the *unchanged*
# upstream agent. Its prompt/memory/execution code remains from the checkout.
stub = types.ModuleType("appworld")
stub.AppWorld = RemoteWorld
stub.load_task_ids = lambda _: ["82e2fac_1"]
sys.modules["appworld"] = stub
sys.path.insert(0, str(SOURCE / "benchmark/appworld"))
agent_module = importlib.import_module("appworld_react_agent")
upstream_agent_class = agent_module.AppworldReactAgent.__ray_metadata__.modified_class
agent_path = pathlib.Path(inspect.getsourcefile(upstream_agent_class)).resolve()
if SOURCE not in agent_path.parents:
    raise RuntimeError("official agent did not import from pinned checkout")
if any(name.endswith("reme_paper_lifecycle") for name in sys.modules):
    raise RuntimeError("local ReMe adaptation imported")

# The official actor creates an SDK client in __init__ even though this fixture
# deliberately never calls ``call_llm``. A sentinel prevents credential access
# while retaining the upstream constructor/prompt code under test.
agent_module.OpenAI = lambda: types.SimpleNamespace()
agent = upstream_agent_class(
    index=0, task_ids=["82e2fac_1"], experiment_name="official_reme_boundary_fixture",
    num_trials=1, max_interactions=30,
)
with RemoteWorld("82e2fac_1", "official_reme_boundary_fixture") as world:
    # This invokes the unmodified upstream prompt builder with public worker
    # fields, but never calls its LLM method.
    agent.prompt_messages(0, 0, [], world)
    world.execute("protocol_counter = 1")
    world.execute("protocol_counter = protocol_counter + 1")
    finish = world.finish_fixture()

assert finish["pass_count"] == 2 and finish["fail_count"] == 0
print(f"upstream_agent={agent_path}")
print("local_reme_adapter=absent")
print("model_calls=0")
print("persistent_actions=2")
print("official_fixture_score=2/2")
