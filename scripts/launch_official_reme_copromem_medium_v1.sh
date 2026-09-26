#!/usr/bin/env bash
set -euo pipefail
root=/mnt/e/Project/AAMAS/COPROMEM
run="$root/artifacts/research/official_reme_copromem_pilot/medium_v1"
mkdir -p "$run"
exec 9>"$run/runner.lock"
flock -n 9 || { echo "medium_v1 runner lock is held" >&2; exit 1; }
if [[ -f "$run/runner.pid" ]]; then
  old="$(cat "$run/runner.pid")"
  if kill -0 "$old" 2>/dev/null && [[ "$(tr '\0' ' ' < "/proc/$old/cmdline" 2>/dev/null || true)" == *"run_official_reme_copromem_medium_v1.py"* ]]; then echo "runner already active" >&2; exit 1; fi
fi
cd "$root"
setsid /usr/bin/env PYTHONPATH=. OFFICIAL_PILOT_C_FLOOR_GB=5 /mnt/e/Project/AAMAS/reme-official-service-v3/bin/python scripts/run_official_reme_copromem_medium_v1.py >"$run/runner.stdout.log" 2>"$run/runner.stderr.log" < /dev/null &
pid=$!; printf '%s\n' "$pid" >"$run/runner.pid"
printf '{"state":"launched","pid":%s}\n' "$pid" >"$run/launcher-status.json"
echo "$pid"
