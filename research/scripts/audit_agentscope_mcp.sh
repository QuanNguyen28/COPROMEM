#!/usr/bin/env bash
set -euo pipefail
source /mnt/e/Project/AAMAS/reme-env/bin/activate
python -m pip show agentscope mcp
python - <<'PY'
from importlib.metadata import distribution
for requirement in distribution("agentscope").requires or []:
    if "mcp" in requirement.lower() or "agentscope" in requirement.lower():
        print(requirement)
PY
python -m pip check
