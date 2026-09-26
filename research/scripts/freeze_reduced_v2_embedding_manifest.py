#!/usr/bin/env python3
"""Freeze reduced_v2 after the no-spend embedding configuration gate."""
from __future__ import annotations

import hashlib
import json
import pathlib

ROOT = pathlib.Path("/mnt/e/Project/AAMAS/COPROMEM")
SOURCE = ROOT / "artifacts/research/official_reme_copromem_pilot/reduced_v1/official_reme_embedding_successor_v1.json"
OUT = ROOT / "artifacts/research/official_reme_copromem_pilot/reduced_v2"


def main() -> None:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    data["protocol"] = "official_reme_copromem_small_scaled_fidelity_reduced_v2"
    data["embedding_route"]["state"] = "configuration_verified_no_spend"
    data["embedding_route"].pop("endpoint", None)  # base URL is local configuration, not manifest data.
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = OUT / "manifest.json"
    text = json.dumps(data, sort_keys=True, indent=2) + "\n"
    if manifest.exists() and manifest.read_text(encoding="utf-8") != text:
        raise RuntimeError("reduced_v2 manifest exists with a different payload")
    manifest.write_text(text, encoding="utf-8")
    (OUT / "manifest.sha256").write_text(digest + "\n", encoding="utf-8")
    print("manifest_sha256=" + digest)
    print("payloads_opened=0")


if __name__ == "__main__":
    main()
