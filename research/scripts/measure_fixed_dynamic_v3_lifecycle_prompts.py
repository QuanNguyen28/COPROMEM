#!/usr/bin/env python3
"""Offline, source-faithful token measurement for the ReMe lifecycle prompts.

It formats the pinned upstream success/failure extraction prompts from the
immutable v1/v2 acquisition histories and records only identities, prompt
digests, token counts, and the chosen ceiling.  It never instantiates an
AppWorld task, sends an HTTP request, or reads credentials.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys
from typing import Any


ROOT = pathlib.Path("/mnt/e/Project/AAMAS/COPROMEM")
UPSTREAM = pathlib.Path("/home/xiqhq/copromem-reme")
V2 = ROOT / "artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v2"
V3 = ROOT / "artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v3"


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def acquisition_rows() -> list[dict[str, Any]]:
    from research.scripts.freeze_corrected_fixed_dynamic_v2_manifest import verify_v1

    carry = verify_v1()
    manifest = json.loads((V2 / "manifest-budget-160.json").read_text(encoding="utf-8"))
    newer: list[dict[str, Any]] = []
    for task_id in manifest["acquisition"]["new_task_ids"]:
        matches = list((V2 / "acquisition").glob(f"{task_id}--*.json"))
        if len(matches) != 1:
            raise RuntimeError(f"expected exactly one immutable v2 artifact for {task_id}")
        path = matches[0]
        row = json.loads(path.read_text(encoding="utf-8"))
        instruction = next((str(message.get("content") or "") for message in row["history"] if message.get("role") == "user"), "")
        if not instruction:
            raise RuntimeError(f"missing public task instruction in {path.name}")
        newer.append({**row, "instruction": instruction, "source_artifact": str(path),
                      "source_artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                      "acquisition_identity": f"{row['task_id']}::seed={row['seed']}::trajectory={row['trial_id']}"})
    rows = carry + newer
    if len(rows) != 32:
        raise RuntimeError("combined immutable acquisition pool must contain 32 trajectories")
    return rows


def main() -> None:
    sys.path.insert(0, str(UPSTREAM))
    from reme.core.schema.message import Trajectory
    from reme.extension.procedural_memory.summary.failure_extraction import FailureExtraction
    from reme.extension.procedural_memory.summary.success_extraction import SuccessExtraction
    from reme.extension.procedural_memory.utils import get_trajectory_context, merge_messages_content
    from research.official_pilot.locked_openrouter import count_chat_tokens

    records: list[dict[str, Any]] = []
    for row in acquisition_rows():
        trajectory = Trajectory(task_id=str(row["task_id"]), messages=row["history"], score=float(row["after_score"]))
        op = SuccessExtraction() if trajectory.score >= 1.0 else FailureExtraction()
        prompt_name = "success_step_task_memory_prompt" if trajectory.score >= 1.0 else "failure_step_task_memory_prompt"
        prompt = op.prompt_format(prompt_name=prompt_name, query=trajectory.metadata.get("query", ""),
                                  step_sequence=merge_messages_content(trajectory.messages),
                                  context=get_trajectory_context(trajectory, trajectory.messages),
                                  outcome="successful" if trajectory.score >= 1.0 else "failed")
        tokens = count_chat_tokens([{"role": "user", "content": prompt}], None)
        records.append({"trajectory_id": row["acquisition_identity"], "task_id": row["task_id"],
                        "kind": "success" if trajectory.score >= 1.0 else "failure", "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                        "prompt_tokens": tokens})
    maximum = max(records, key=lambda item: int(item["prompt_tokens"]))
    # 65,536 leaves more than 2x the observed maximum headroom.  Escalate only
    # when a later frozen evidence set actually requires it.
    ceiling = 65_536 if int(maximum["prompt_tokens"]) <= 65_536 else 131_072
    result = {"source": {"reme_commit": "2f37a159b72a04ac1885a7db7f1a663a833e7791", "prompt_measurement": "pinned_upstream_direct_format"},
              "combined_trajectories": len(records), "maximum": maximum, "selected_lifecycle_input_ceiling": ceiling,
              "records": records, "records_sha256": canonical_hash(records)}
    V3.mkdir(parents=True, exist_ok=True)
    (V3 / "lifecycle-prompt-measurement.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"combined_trajectories": len(records), "max_prompt_tokens": maximum["prompt_tokens"], "selected_ceiling": ceiling}, sort_keys=True))


if __name__ == "__main__":
    main()
