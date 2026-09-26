#!/usr/bin/env python3
"""One authorized OpenRouter embedding-only canary for amendment v2."""
from __future__ import annotations

import json, os, pathlib, sys

ROOT = pathlib.Path("/mnt/e/Project/AAMAS/COPROMEM"); sys.path.insert(0, str(ROOT))
from research.official_pilot.locked_openrouter import AppendOnlyLedger, DispatchFailure, LockedEmbeddings

RUN = ROOT / "artifacts/research/official_reme_copromem_pilot/reduced_v2"
PROGRESS = ROOT / "artifacts/research/official_reme_copromem_pilot/progress.jsonl"


def key() -> str:
    for raw in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if raw.startswith("OPENROUTER_API_KEY="):
            return raw.split("=", 1)[1].strip().strip("'\"")
    return ""


def main() -> None:
    out = RUN / "embedding-canary-v5-openrouter-azure.json"
    if out.exists(): raise RuntimeError("OpenRouter embedding canary already recorded")
    api_key = key()
    if not api_key: raise RuntimeError("OpenRouter credential unavailable")
    client = LockedEmbeddings(api_key=api_key, base_url="https://openrouter.ai/api/v1",
        ledger=AppendOnlyLedger(RUN / "successor-ledger.jsonl", 35.0), progress=PROGRESS,
        role="reme_embedding_canary_v4_openrouter", allowed_model="openai/text-embedding-3-small",
        provider="azure", provider_only="azure", usd_per_input_token=0.02 / 1_000_000)
    try:
        response = client.create(model="openai/text-embedding-3-small", input="vector-store interface canary",
                                 dimensions=1024, encoding_format="float")
        dimension = len(getattr(response.data[0], "embedding", [])) if response.data else 0
        record = {**(client.last_record or {}), "state":"passed" if dimension == 1024 else "failed_validation",
                  "model":"openai/text-embedding-3-small", "dimensions":1024,
                  "output_dimension":dimension, "vector_count":len(response.data)}
    except DispatchFailure:
        record = {"state":"failed", "model":"openai/text-embedding-3-small", "dimensions":1024,
                  "diagnostics":"see sanitized progress event"}
    with out.open("x", encoding="utf-8") as f:
        json.dump(record, f, sort_keys=True); f.write("\n"); f.flush(); os.fsync(f.fileno())
    if record["state"] != "passed": raise RuntimeError("OpenRouter embedding canary failed")
    print("reduced_v2_openrouter_embedding_canary=passed")


if __name__ == "__main__": main()
