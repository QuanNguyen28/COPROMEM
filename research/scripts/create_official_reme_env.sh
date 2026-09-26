#!/usr/bin/env bash
set -euo pipefail

ENV_DIR=/mnt/e/Project/AAMAS/reme-official-v3
SOURCE_DIR=/home/xiqhq/copromem-reme
CACHE_DIR=/mnt/e/Project/AAMAS/reme-pip-cache
TMP_DIR=/mnt/e/Project/AAMAS/reme-install-tmp
MANIFEST_DIR=/mnt/e/Project/AAMAS/COPROMEM/artifacts/research/reme_copromem_comparison/official_upstream_scaled_fidelity/environment

mkdir -p "$CACHE_DIR" "$TMP_DIR" "$MANIFEST_DIR"
export TMPDIR="$TMP_DIR"
export PIP_CACHE_DIR="$CACHE_DIR"
export PIP_DISABLE_PIP_VERSION_CHECK=1

if [[ ! -x "$ENV_DIR/bin/python" ]]; then
  python3.12 -m venv "$ENV_DIR"
fi

"$ENV_DIR/bin/python" -m pip install \
  --cache-dir "$CACHE_DIR" \
  "agentscope==1.0.20" \
  "flowllm[reme]==0.2.0.10" \
  "ray==2.58.0" \
  -e "$SOURCE_DIR"

"$ENV_DIR/bin/python" -m pip check
"$ENV_DIR/bin/python" -m pip freeze --all | LC_ALL=C sort > "$MANIFEST_DIR/pip-freeze.txt"
"$ENV_DIR/bin/python" -m pip --version > "$MANIFEST_DIR/pip-version.txt"
git -C "$SOURCE_DIR" remote get-url origin > "$MANIFEST_DIR/reme-remote.txt"
git -C "$SOURCE_DIR" rev-parse HEAD > "$MANIFEST_DIR/reme-commit.txt"
git -C "$SOURCE_DIR" status --porcelain > "$MANIFEST_DIR/reme-status.txt"
du -sh "$ENV_DIR" > "$MANIFEST_DIR/reme-env-disk-usage.txt"
df -h / /mnt/e > "$MANIFEST_DIR/filesystem-usage.txt"
