#!/usr/bin/env bash
set -euo pipefail
source /mnt/e/Project/AAMAS/reme-env/bin/activate
cd /home/xiqhq/copromem-reme/benchmark/appworld
python - <<'PY'
import importlib
import sys
import agentscope
print("python=" + sys.version.split()[0])
print("agentscope=" + getattr(agentscope, "__version__", "unknown"))
agent = importlib.import_module("appworld_react_agent")
runner = importlib.import_module("run_appworld")
print("agent_file=" + agent.__file__)
print("runner_file=" + runner.__file__)
print("agent_class=" + agent.AppworldReactAgent.__module__)
PY
