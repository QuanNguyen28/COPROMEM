#!/usr/bin/env bash
set -euo pipefail
ENV_DIR=/mnt/e/Project/AAMAS/reme-official-v3
"$ENV_DIR/bin/python" - <<'PY'
from importlib.metadata import distribution
for name in ('fastmcp', 'flowllm', 'reme-ai'):
    dist = distribution(name)
    print(f'{name}=={dist.version}')
    for requirement in dist.requires or []:
        if any(token in requirement.lower() for token in ('mcp', 'agentscope', 'pydantic')):
            print(f'  requires: {requirement}')
PY
"$ENV_DIR/bin/python" -m pip index versions fastmcp | head -20
