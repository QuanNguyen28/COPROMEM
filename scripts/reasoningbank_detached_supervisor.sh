#!/usr/bin/env bash
# Supervise one detached child after the credential wrapper has performed its
# foreground source-and-exec boundary.  Records contain no command arguments,
# paths, environment values, prompts, or provider material.
set -euo pipefail
set +x

usage() { echo "usage: $0 --stage-dir <absolute-dir> --cwd <absolute-dir> -- <command...>" >&2; exit 64; }
[[ "$#" -ge 6 && "$1" == "--stage-dir" && "$3" == "--cwd" && "$5" == "--" ]] || usage
stage_dir="$2"
cwd="$4"
shift 5
[[ "$stage_dir" == /* && "$cwd" == /* && "$#" -gt 0 ]] || usage
mkdir -p "$stage_dir"
cd "$cwd"

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
