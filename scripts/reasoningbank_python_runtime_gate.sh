#!/usr/bin/env bash
# Runs after credential sourcing and before the detached supervisor starts the
# engineering runner.  Stage records contain only a result and exit status.
set -euo pipefail
set +x

usage() { echo "usage: $0 --python <absolute> --runtime-root <absolute> --agent-root <absolute> --run <absolute> --stage-dir <absolute> -- <command...>" >&2; exit 64; }
[[ "$#" -ge 12 && "$1" == "--python" && "$3" == "--runtime-root" && "$5" == "--agent-root" && "$7" == "--run" && "$9" == "--stage-dir" && "${11}" == "--" ]] || usage
python="$2"; runtime_root="$4"; agent_root="$6"; run="$8"; stage_dir="${10}"; shift 11
[[ "$python" == /* && "$runtime_root" == /* && "$agent_root" == /* && "$run" == /* && "$stage_dir" == /* && "$#" -gt 0 ]] || usage

record() {
  local name="$1" stage="$2" code="$3" tmp
  mkdir -p "$stage_dir"
  tmp="$(mktemp "$stage_dir/.${name}.XXXXXX")"
  printf '{"version":"reasoningbank-detached-launch-v1","stage":"%s","pid":%s,"exit_code":%s}\n' "$stage" "$$" "$code" > "$tmp"
  mv -f "$tmp" "$stage_dir/$name.json"
}
if "$python" "$runtime_root/scripts/check_reasoningbank_appworld_runtime.py" \
    --expected-python "$python" --agent-root "$agent_root" --runtime-root "$runtime_root" \
    --output "$run/python-runtime-identity.json"; then
  record python-dependency-gate python-dependency-gate-passed 0
else
  code=$?; record python-dependency-gate python-dependency-gate-failed "$code"; exit "$code"
fi
exec "$@"
