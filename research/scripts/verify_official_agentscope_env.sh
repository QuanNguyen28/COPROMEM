#!/usr/bin/env bash
# Verify the isolated legacy-MCP AgentScope environment used by the official
# ReMe deployment.  This intentionally does not import FlowLLM or the local
# lifecycle adapter: those live in separate processes.
set -euo pipefail

ENV_DIR=/mnt/e/Project/AAMAS/reme-official-agentscope-v3
OUT_DIR=/mnt/e/Project/AAMAS/COPROMEM/artifacts/research/official_reme_copromem_pilot/environment
mkdir -p "$OUT_DIR"

"$ENV_DIR/bin/python" -m pip check | tee "$OUT_DIR/agentscope-pip-check.txt"
"$ENV_DIR/bin/python" -m pip freeze --all | LC_ALL=C sort \
  > "$OUT_DIR/agentscope-pip-freeze.txt"
"$ENV_DIR/bin/python" - <<'PY' | tee "$OUT_DIR/agentscope-imports.txt"
import importlib
import importlib.metadata
import pathlib
import sys

expected = {
    "agentscope": "1.0.20",
    "mcp": "1.30.0",
    "greenlet": "3.5.6",
}
for distribution, version in expected.items():
    actual = importlib.metadata.version(distribution)
    print(f"{distribution}={actual}")
    if actual != version:
        raise RuntimeError(f"{distribution} expected {version}, got {actual}")

for module_name in (
    "agentscope",
    "mcp",
    "mcp.client.streamable_http",
    "greenlet",
):
    module = importlib.import_module(module_name)
    print(f"{module_name}={pathlib.Path(module.__file__).resolve()}")

# AgentScope 1.0.20 requires this legacy MCP 1.x API spelling.
streamable = importlib.import_module("mcp.client.streamable_http")
if not hasattr(streamable, "streamablehttp_client"):
    raise RuntimeError("MCP legacy streamablehttp_client is unavailable")
if any("reme_paper_lifecycle" in name for name in sys.modules):
    raise RuntimeError("local ReMe adaptation imported into AgentScope verifier")
print("local_reme_adapter=absent")
PY
