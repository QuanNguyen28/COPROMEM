#!/usr/bin/env python3
"""Freeze reduced official-pilot IDs without constructing AppWorld tasks."""
from __future__ import annotations

import hashlib
import json
import pathlib

from appworld import load_task_ids

ROOT = pathlib.Path("/mnt/e/Project/AAMAS/COPROMEM")
OUT = ROOT / "artifacts/research/official_reme_copromem_pilot/reduced_v1"


def canonical_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def flatten(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for group in value for item in flatten(group)]
    raise TypeError(type(value).__name__)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    # AppWorld's split inventory loader returns IDs only; no AppWorld instance
    # is constructed and no task instruction/database/checker is read here.
    train = sorted(flatten(load_task_ids("train")))
    test = sorted(flatten(load_task_ids("test_normal")))
    manifest = {
        "protocol": "official_reme_copromem_small_scaled_fidelity_v1",
        "label": "small scaled-fidelity pilot; not a full ReMe reproduction or definitive efficacy study",
        "source": {"repo": "https://github.com/agentscope-ai/ReMe.git",
                   "commit": "2f37a159b72a04ac1885a7db7f1a663a833e7791",
                   "digest": "5d2706b7b0e304475c71778b9336a733874e2492f4fdb5d311a2914751fe47fa"},
        "route": {"endpoint": "https://openrouter.ai/api/v1/chat/completions",
                  "model": "deepseek/deepseek-v4.1-flash", "provider_only": ["deepseek"],
                  "allow_fallbacks": False, "reasoning_effort": "none", "stream": False,
                  "parallel_tool_calls": False, "max_completion_tokens": 1024,
                  "max_input_tokens": 16384},
        "acquisition": {"split": "train", "task_ids": train[:6], "seeds": [7101, 7102, 7103, 7104, 7105, 7106],
                        "trajectories_per_task": 1},
        "evaluation": {"split": "test_normal", "task_ids": test[:4], "seeds": [8101, 8102, 8103, 8104],
                       "trials_per_task": 4},
        "arms": ["no_memory", "official_upstream_reme_fixed", "official_upstream_reme_dynamic", "copromem_v2"],
        "max_actions": 30,
        "metrics": ["Avg@4", "Pass@4"],
        "concurrency_max": 2,
        "isolation_required": ["worker", "conversation", "memory_trial_state", "journal", "reservation", "scorer", "artifact_directory"],
        "budget": {"absolute_usd": 35.0, "contingency_fraction": 0.15,
                   "input_usd_per_million": 0.15, "completion_usd_per_million": 0.60},
    }
    if len(set(manifest["acquisition"]["task_ids"] + manifest["evaluation"]["task_ids"])) != 10:
        raise RuntimeError("allocation is not disjoint")
    payload = json.dumps(manifest, sort_keys=True, indent=2) + "\n"
    path = OUT / "manifest.json"
    if path.exists() and path.read_text(encoding="utf-8") != payload:
        raise RuntimeError("frozen manifest already exists with different content")
    path.write_text(payload, encoding="utf-8")
    (OUT / "manifest.sha256").write_text(canonical_hash(manifest) + "\n", encoding="utf-8")
    print(f"manifest={path}")
    print(f"sha256={canonical_hash(manifest)}")
    print("payloads_opened=0")


if __name__ == "__main__":
    main()
