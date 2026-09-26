#!/usr/bin/env bash
set -euo pipefail
temp=/mnt/e/Project/AAMAS/reme-install-tmp/mcp-audit
mkdir -p "$temp"
/mnt/e/Project/AAMAS/reme-env/bin/python -m pip download --no-deps --dest "$temp" mcp==1.13.1
/mnt/e/Project/AAMAS/reme-env/bin/python -m pip download --no-deps --dest "$temp" mcp==1.30.0
/mnt/e/Project/AAMAS/reme-env/bin/python - "$temp" <<'PY'
import glob
import sys
import zipfile
for version in ("1.13.1", "1.30.0"):
    wheel = glob.glob(sys.argv[1] + "/mcp-" + version + "-*.whl")[0]
    with zipfile.ZipFile(wheel) as archive:
        source = archive.read("mcp/client/streamable_http.py").decode("utf-8")
    print(version + ":streamablehttp_client=" + str("streamablehttp_client" in source))
    print(version + ":streamable_http_client=" + str("streamable_http_client" in source))
PY
