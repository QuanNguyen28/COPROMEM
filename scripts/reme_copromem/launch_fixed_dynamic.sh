#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
run="$root/artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v4"
cd "$root"
mkdir -p "$run/logs"
if [[ -f "$run/runner.lock" ]]; then
  pid="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pid"])' "$run/runner.lock")"
  if kill -0 "$pid" 2>/dev/null; then
    echo "runner already active: $pid" >&2
    exit 1
  fi
  rm -f "$run/runner.lock"
fi
nohup env COPROMEM_ROOT="$root" PYTHONPATH="$root/src:$root" "${COPROMEM_REME_PYTHON:-/mnt/e/Project/AAMAS/reme-upstream-fixed-dynamic/bin/python}" \
  scripts/reme_copromem/run_fixed_dynamic.py >"$run/logs/runner.stdout.log" 2>&1 < /dev/null &
pid=$!
printf '%s\n' "$pid" >"$run/runner.pid"
echo "$pid"
