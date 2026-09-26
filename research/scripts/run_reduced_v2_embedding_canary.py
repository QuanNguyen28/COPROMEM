#!/usr/bin/env python3
"""One minimal, ledgered DashScope embedding-only canary for reduced-v2."""
from __future__ import annotations

import json
import os
import pathlib
import sys
import urllib.parse

ROOT = pathlib.Path("/mnt/e/Project/AAMAS/COPROMEM")
sys.path.insert(0, str(ROOT))
from research.official_pilot.locked_openrouter import AppendOnlyLedger, DispatchFailure, LockedEmbeddings

RUN = ROOT / "artifacts/research/official_reme_copromem_pilot/reduced_v2"
PROGRESS = ROOT / "artifacts/research/official_reme_copromem_pilot/progress.jsonl"


def env_values() -> dict[str, str]:
    result: dict[str, str] = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1); result[key.strip()] = value.strip().strip("'\"")
    return result


def main() -> None:
    # v1 is immutable (international endpoint, entitlement failure).  This is
    # a distinct, one-shot workspace/Singapore configuration diagnostic.
    out = RUN / "embedding-canary-v3-singapore.json"
    if out.exists(): raise RuntimeError("embedding canary already has a durable result")
    values = env_values()
    base = values.get("FLOW_EMBEDDING_BASE_URL", "")
    host = urllib.parse.urlparse(base).hostname or ""
    if not host.endswith(".ap-southeast-1.maas.aliyuncs.com"):
        raise RuntimeError("configured endpoint is not the authorized Singapore DashScope endpoint")
    key = values.get("FLOW_EMBEDDING_API_KEY")
    if not key: raise RuntimeError("embedding credential absent")
    ledger = AppendOnlyLedger(RUN / "successor-ledger.jsonl", 35.0)
    client = LockedEmbeddings(api_key=key, base_url=base, ledger=ledger, progress=PROGRESS,
                              role="reme_embedding_canary_v3_singapore")
    try:
        response = client.create(model="text-embedding-v4", input="vector-store interface canary",
                                 dimensions=1024, encoding_format="float")
        valid = len(response.data) == 1 and len(getattr(response.data[0], "embedding", [])) == 1024
        record = {"state":"passed" if valid else "failed_validation", "model":"text-embedding-v4",
                  "dimensions":1024, "vector_count":len(response.data), "vector_dimensions":
                  len(getattr(response.data[0], "embedding", [])) if response.data else 0}
    except DispatchFailure:
        record = {"state":"failed", "model":"text-embedding-v4", "dimensions":1024,
                  "diagnostics":"see sanitized progress event"}
    with out.open("x", encoding="utf-8") as f:
        json.dump(record, f, sort_keys=True); f.write("\n"); f.flush(); os.fsync(f.fileno())
    if record["state"] != "passed": raise RuntimeError("embedding canary failed")
    print("reduced_v2_embedding_canary=passed")


if __name__ == "__main__": main()
