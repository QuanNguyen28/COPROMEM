#!/usr/bin/env python3
"""Freeze 40 new AppWorld test-normal IDs without opening task payloads."""
from __future__ import annotations

import hashlib
import json
import pathlib

ROOT = pathlib.Path("/mnt/e/Project/AAMAS/COPROMEM")
OLD = ROOT / "artifacts/research/official_reme_copromem_pilot/reduced_v2"
OUT = ROOT / "artifacts/research/official_reme_copromem_pilot/medium_v1"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def main() -> None:
    from appworld import load_task_ids

    old = json.loads((OLD / "manifest.json").read_text(encoding="utf-8"))
    excluded = set(old["evaluation"]["task_ids"])
    inventory = list(load_task_ids("test_normal"))
    ranked = sorted((task for task in inventory if task not in excluded),
                    key=lambda task: hashlib.sha256(("copromem-medium-v1:" + task).encode()).hexdigest())
    selected = ranked[:40]
    if len(selected) != 40 or set(selected) & excluded:
        raise RuntimeError("unable to freeze 40 disjoint test-normal IDs")
    acquisition = []
    for path in sorted((OLD / "acquisition").glob("*.json")):
        acquisition.append({"path": str(path.relative_to(ROOT)),
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    if len(acquisition) != 5:
        raise RuntimeError("expected exactly five durable frozen acquisition artifacts")
    manifest = {
        "protocol": "official_reme_copromem_medium_v1",
        "label": "40-task exploratory successor; faithful adaptation, not exact ReMe reproduction",
        "source_manifest_sha256": (OLD / "manifest.sha256").read_text().strip(),
        "acquisition": old["acquisition"],
        "acquisition_source": {"mode": "immutable carry-forward", "artifacts": acquisition},
        "evaluation": {"split": "test_normal", "task_ids": selected,
                       "seeds": [9101, 9102, 9103, 9104], "trials_per_task": 4},
        "arms": ["no_memory", "official_upstream_reme_fixed",
                 "official_upstream_reme_dynamic", "copromem_v2"],
        "max_actions": 30,
        "route": old["route"],
        "embedding_route": {"provider": "OpenRouter Azure", "model": "openai/text-embedding-3-small",
                            "dimensions": 1024},
        "source": old["source"],
        "budget": {"hard_cap_usd": 140.0, "all_inclusive_conservative_usd": 139.52448543765},
        "selection": {"method": "SHA-256 rank of test-normal IDs",
                      "salt": "copromem-medium-v1", "payloads_opened_before_freeze": False,
                      "excluded_prior_evaluation_ids": sorted(excluded)},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    data = canonical(manifest)
    target, digest = OUT / "manifest.json", hashlib.sha256(data).hexdigest()
    if target.exists() and target.read_bytes() != data:
        raise RuntimeError("medium_v1 manifest already exists with different contents")
    target.write_bytes(data)
    (OUT / "manifest.sha256").write_text(digest + "\n", encoding="utf-8")
    print(json.dumps({"manifest_sha256": digest, "evaluation_tasks": len(selected),
                      "acquisition_artifacts": len(acquisition)}, sort_keys=True))


if __name__ == "__main__":
    main()
