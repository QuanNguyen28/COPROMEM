#!/usr/bin/env bash
# Dispatch one WSL child in a new session.  `setsid -f` is required because a
# background job owned by the one-shot wsl.exe shell can be terminated when its
# Windows parent exits before the child reaches Python.
set -euo pipefail
set +x

usage() { echo "usage: $0 --run <absolute-dir> --stage-dir <absolute-dir> --python <absolute> --runtime-root <absolute> --agent-root <absolute> -- <command...>" >&2; exit 64; }
[[ "$#" -ge 13 && "$1" == "--run" && "$3" == "--stage-dir" && "$5" == "--python" && "$7" == "--runtime-root" && "$9" == "--agent-root" && "${11}" == "--" ]] || usage
run="$2"; stage_dir="$4"; python="$6"; runtime_root="$8"; agent_root="${10}"
shift 11
[[ "$run" == /* && "$stage_dir" == /* && "$python" == /* && "$runtime_root" == /* && "$agent_root" == /* && "$#" -gt 0 ]] || usage
credential_wrapper="$(dirname "$0")/launch_reasoningbank_appworld_engineering_wsl.sh"
supervisor="$(dirname "$0")/reasoningbank_detached_supervisor.sh"
python_gate="$(dirname "$0")/reasoningbank_python_runtime_gate.sh"

record() {
  local name="$1" stage="$2" code="$3" tmp
  mkdir -p "$stage_dir"
  tmp="$(mktemp "$stage_dir/.${name}.XXXXXX")"
  printf '{"version":"reasoningbank-detached-launch-v1","stage":"%s","pid":%s,"exit_code":%s}\n' \
    "$stage" "$$" "$code" > "$tmp"
  mv -f "$tmp" "$stage_dir/$name.json"
}
terminal() {
  local code=$?
  [[ "$code" -eq 0 || -e "$stage_dir/launch-terminal.json" ]] || record launch-terminal detached-dispatch-failed "$code"
}
trap terminal EXIT
[[ -x "$credential_wrapper" || -f "$credential_wrapper" ]] || exit 41
[[ -x "$supervisor" || -f "$supervisor" ]] || exit 41
[[ -x "$python_gate" || -f "$python_gate" ]] || exit 41
mkdir -p "$run" "$stage_dir"
record launcher-received launcher-received 0
# Create both streams before detaching, so a pre-Python failure is observable.
: > "$run/runner.stdout.log"
: > "$run/runner.stderr.log"
record stdio-ready stdio-ready 0
setsid -f env REASONINGBANK_LAUNCH_STAGE_DIR="$stage_dir" "$credential_wrapper" \
  "$python_gate" --python "$python" --runtime-root "$runtime_root" --agent-root "$agent_root" --run "$run" --stage-dir "$stage_dir" -- \
  "$supervisor" --stage-dir "$stage_dir" --cwd "$run" -- "$@" \
  > "$run/runner.stdout.log" 2> "$run/runner.stderr.log" < /dev/null
record detached-dispatched detached-dispatched 0
trap - EXIT
