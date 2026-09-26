#!/usr/bin/env bash
set -euo pipefail
ENV_DIR=/mnt/e/Project/AAMAS/reme-official-v3
"$ENV_DIR/bin/python" - <<'PY'
from importlib.metadata import distribution, version
for name in ('agentscope', 'mcp', 'flowllm', 'ray', 'reme-ai'):
    dist = distribution(name)
    print(f'{name}=={dist.version}')
    for requirement in dist.requires or []:
        if 'mcp' in requirement.lower():
            print(f'  requires: {requirement}')
PY
"$ENV_DIR/bin/python" -m pip index versions mcp | head -25
