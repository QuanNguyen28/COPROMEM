#!/usr/bin/env bash
set -euo pipefail
source /home/xiqhq/copromem-appworld/venv/bin/activate
cd /home/xiqhq/copromem-reme/benchmark/appworld
python - <<'PY'
import importlib
import sys
for name in ("appworld", "ray", "openai", "jinja2", "loguru", "requests", "dotenv"):
    module = importlib.import_module(name)
    print(name + "=" + getattr(module, "__file__", "built-in"))
agent = importlib.import_module("appworld_react_agent")
runner = importlib.import_module("run_appworld")
print("agent_file=" + agent.__file__)
print("runner_file=" + runner.__file__)
print("agent_class=" + agent.AppworldReactAgent.__module__)
print("python=" + sys.version.split()[0])
PY
