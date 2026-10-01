#!/usr/bin/env bash
# Supervise one detached child after the credential wrapper has performed its
# foreground source-and-exec boundary.  Records contain no command arguments,
# paths, environment values, prompts, or provider material.
set -euo pipefail
set +x

usage() { echo "usage: $0 --stage-dir <absolute-dir> -- <command...>" >&2; exit 64; }
[[ "$#" -ge 4 && "$1" == "--stage-dir" && "$3" == "--" ]] || usage
stage_dir="$2"
shift 3
[[ "$stage_dir" == /* && "$#" -gt 0 ]] || usage
mkdir -p "$stage_dir"

record() {
  local name="$1" stage="$2" code="$3" tmp
  tmp="$(mktemp "$stage_dir/.${name}.XXXXXX")"
  printf '{"version":"reasoningbank-detached-launch-v1","stage":"%s","pid":%s,"exit_code":%s}\n' \
    "$stage" "$$" "$code" > "$tmp"
  mv -f "$tmp" "$stage_dir/$name.json"
}
terminal() {
  local code=$?
  [[ -e "$stage_dir/child-terminal.json" ]] || record child-terminal child-exited "$code"
}
trap terminal EXIT
record child-started child-started 0
"$@"
