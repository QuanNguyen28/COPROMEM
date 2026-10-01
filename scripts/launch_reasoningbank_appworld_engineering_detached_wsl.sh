#!/usr/bin/env bash
# Dispatch one WSL child in a new session.  `setsid -f` is required because a
# background job owned by the one-shot wsl.exe shell can be terminated when its
# Windows parent exits before the child reaches Python.
set -euo pipefail
set +x

usage() { echo "usage: $0 --run <absolute-dir> --stage-dir <absolute-dir> -- <command...>" >&2; exit 64; }
[[ "$#" -ge 6 && "$1" == "--run" && "$3" == "--stage-dir" && "$5" == "--" ]] || usage
run="$2"
stage_dir="$4"
shift 5
[[ "$run" == /* && "$stage_dir" == /* && "$#" -gt 0 ]] || usage
credential_wrapper="$(dirname "$0")/launch_reasoningbank_appworld_engineering_wsl.sh"
supervisor="$(dirname "$0")/reasoningbank_detached_supervisor.sh"

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
mkdir -p "$run" "$stage_dir"
record launcher-received launcher-received 0
# Create both streams before detaching, so a pre-Python failure is observable.
: > "$run/runner.stdout.log"
: > "$run/runner.stderr.log"
record stdio-ready stdio-ready 0
setsid -f env REASONINGBANK_LAUNCH_STAGE_DIR="$stage_dir" "$credential_wrapper" \
  "$supervisor" --stage-dir "$stage_dir" --cwd "$run" -- "$@" \
  > "$run/runner.stdout.log" 2> "$run/runner.stderr.log" < /dev/null
record detached-dispatched detached-dispatched 0
trap - EXIT
