#!/usr/bin/env bash
# Launch exactly one detached reduced-v2 coordinator.  The coordinator owns
# all model dispatch, checkpoints and service subprocesses; this wrapper never
# reads credentials or task data.
set -euo pipefail
root=/mnt/e/Project/AAMAS/COPROMEM
run="$root/artifacts/research/official_reme_copromem_pilot/reduced_v2"
mkdir -p "$run"
lock="$run/runner.lock"
exec 9>"$lock"
if ! flock -n 9; then
  echo "runner launch lock is held" >&2
  exit 1
fi
if [[ -f "$run/runner.pid" ]]; then
  old_pid="$(cat "$run/runner.pid")"
  # PID reuse is not evidence of an active coordinator.  Require the exact
  # runner command before refusing a resume.
  if kill -0 "$old_pid" 2>/dev/null && [[ "$(tr '\0' ' ' < "/proc/$old_pid/cmdline" 2>/dev/null || true)" == *"run_official_reme_copromem_reduced_v2.py"* ]]; then
    echo "runner already active" >&2
    exit 1
  fi
fi
cd "$root"
setsid /usr/bin/env PYTHONPATH=. /mnt/e/Project/AAMAS/reme-official-service-v3/bin/python \
  scripts/run_official_reme_copromem_reduced_v2.py \
  >"$run/runner.stdout.log" 2>"$run/runner.stderr.log" < /dev/null &
pid=$!
printf '%s\n' "$pid" > "$run/runner.pid"
printf '{"state":"launched","pid":%s,"stdout":"runner.stdout.log","stderr":"runner.stderr.log"}\n' "$pid" > "$run/launcher-status.json"
echo "$pid"
