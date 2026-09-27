#!/usr/bin/env bash
# Zero-cost contract audit of the legacy ReMe AppWorld service.  A caller may
# provide a distinct output directory as its only argument.
set -eu

ROOT=/mnt/e/Project/AAMAS/COPROMEM
PYTHON=/mnt/e/Project/AAMAS/reme-upstream-fixed-dynamic/bin/python
RUN=${1:-"$ROOT/artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v1/pinned_service_contract_clean"}

PYTHONPATH="$ROOT" \
OFFICIAL_REME_PYTHON="$PYTHON" \
OFFICIAL_REME_CONTRACT_RUN="$RUN" \
"$PYTHON" "$ROOT/research/scripts/verify_pinned_reme_appworld_contract.py"
