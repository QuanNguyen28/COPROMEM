#!/usr/bin/env bash
set -euo pipefail
ENV_DIR=/mnt/e/Project/AAMAS/reme-official-v3
CACHE_DIR=/mnt/e/Project/AAMAS/reme-pip-cache
TMP_DIR=/mnt/e/Project/AAMAS/reme-install-tmp/fastmcp-2141-audit
mkdir -p "$TMP_DIR"
"$ENV_DIR/bin/python" -m pip download --no-deps --dest "$TMP_DIR" --cache-dir "$CACHE_DIR" 'fastmcp==2.14.1' >/dev/null
wheel=$(find "$TMP_DIR" -maxdepth 1 -name 'fastmcp-2.14.1-*.whl' -print -quit)
"$ENV_DIR/bin/python" - "$wheel" <<'PY'
import sys
import zipfile

with zipfile.ZipFile(sys.argv[1]) as wheel:
    metadata = next(n for n in wheel.namelist() if n.endswith('.dist-info/METADATA'))
    for line in wheel.read(metadata).decode().splitlines():
        if line.startswith(('Name:', 'Version:', 'Requires-Dist:')):
            print(line)
PY
