#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
checkout="${1:-$repo_root/external/reasoning-bank}"
source_repo="${REASONING_BANK_SOURCE:-https://github.com/google-research/reasoning-bank.git}"
pinned_commit="ed80611"
runtime_patch="$repo_root/integrations/reasoning_bank/upstream.patch"
adapter_source="$repo_root/integrations/reasoning_bank/copromem_adapter.py"
adapter_target="$checkout/WebArena/copromem_adapter.py"

if [[ ! -d "$checkout/.git" ]]; then
    if [[ -e "$checkout" ]]; then
        echo "Refusing to replace existing non-Git directory: $checkout" >&2
        exit 1
    fi
    git clone "$source_repo" "$checkout"
    git -C "$checkout" -c advice.detachedHead=false checkout --detach "$pinned_commit"
fi

actual_commit="$(git -C "$checkout" rev-parse --short=7 HEAD)"
if [[ "$actual_commit" != "$pinned_commit" ]]; then
    echo "Expected ReasoningBank commit $pinned_commit, found $actual_commit in $checkout" >&2
    exit 1
fi

if git -C "$checkout" apply --reverse --check "$runtime_patch" 2>/dev/null; then
    echo "ReasoningBank runtime patch is already applied."
elif git -C "$checkout" apply --check "$runtime_patch" 2>/dev/null; then
    git -C "$checkout" apply "$runtime_patch"
    echo "Applied ReasoningBank runtime patch."
else
    echo "ReasoningBank checkout has overlapping edits; inspect it before applying the patch." >&2
    exit 1
fi

if [[ -e "$adapter_target" ]]; then
    if ! cmp -s "$adapter_source" "$adapter_target"; then
        echo "Adapter already exists with different content: $adapter_target" >&2
        exit 1
    fi
else
    cp "$adapter_source" "$adapter_target"
    echo "Installed COPROMEM adapter."
fi

echo "ReasoningBank integration is ready at $checkout"
