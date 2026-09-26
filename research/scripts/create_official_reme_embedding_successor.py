#!/usr/bin/env python3
"""Freeze the no-spend successor protocol for official ReMe embeddings."""
from __future__ import annotations

import hashlib
import json
import pathlib

ROOT = pathlib.Path("/mnt/e/Project/AAMAS/COPROMEM")
RUN = ROOT / "artifacts/research/official_reme_copromem_pilot/reduced_v1"
SOURCE = RUN / "manifest.json"
TARGET = RUN / "official_reme_embedding_successor_v1.json"


def main() -> None:
    value = json.loads(SOURCE.read_text(encoding="utf-8"))
    value["protocol"] = "official_reme_copromem_small_scaled_fidelity_embedding_successor_v1"
    value["upstream_reme_executor"] = {"protocol": "plain_code_completion", "native_tools": False}
    value["embedding_route"] = {
        "provider": "Alibaba Cloud Model Studio (DashScope)",
        "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
        "model": "text-embedding-v4",
        "credential_env": "FLOW_EMBEDDING_API_KEY",
        "base_url_env": "FLOW_EMBEDDING_BASE_URL",
        "dimensions": 1024,
        "request": {"model": "text-embedding-v4", "input": "upstream ReMe vector text only",
                    "dimensions": 1024, "encoding_format": "float"},
        "prohibited": ["action generation", "memory generation", "reflection", "decision generation"],
        "state": "credential_pending_no_dispatch",
    }
    payload = json.dumps(value, sort_keys=True, indent=2) + "\n"
    digest = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if TARGET.exists() and TARGET.read_text(encoding="utf-8") != payload:
        raise RuntimeError("successor manifest already exists with different content")
    TARGET.write_text(payload, encoding="utf-8")
    TARGET.with_suffix(".sha256").write_text(digest + "\n", encoding="utf-8")
    print("successor_manifest_sha256=" + digest)
    print("payloads_opened=0")


if __name__ == "__main__":
    main()
