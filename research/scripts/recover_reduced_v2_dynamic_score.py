#!/usr/bin/env python3
"""Recover one missing official score by exact, zero-model native action replay."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sys
import time

ROOT = pathlib.Path("/mnt/e/Project/AAMAS/COPROMEM")
sys.path.insert(0, str(ROOT))
RUN = ROOT / "artifacts/research/official_reme_copromem_pilot/reduced_v2"
SOURCE_JOURNAL = RUN / "journals/evaluation_official_upstream_reme_dynamic_024c982_2_seed_8102_trial_2.jsonl"
RECOVERY_JOURNAL = RUN / "journals/recovery_official_upstream_reme_dynamic_024c982_2_seed_8102_trial_2.jsonl"
ARTIFACT = RUN / "evaluation/official_upstream_reme_dynamic-024c982_2-8102.json"
PROGRESS = ROOT / "artifacts/research/official_reme_copromem_pilot/progress.jsonl"
TASK_ID = "024c982_2"
SEED = 8102
TRIAL = 2
ARM = "official_upstream_reme_dynamic"
KEY = f"evaluation:{ARM}:{TASK_ID}:seed={SEED}:trial={TRIAL}"


def append(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main() -> None:
    if ARTIFACT.exists():
        print("recovery already exists")
        return
    events = [json.loads(line) for line in SOURCE_JOURNAL.read_text(encoding="utf-8").splitlines() if line]
    submitted = {int(x["index"]): x for x in events if x.get("event") == "action_submitted"}
    applied = {int(x["index"]): x for x in events if x.get("event") == "action_applied"}
    if sorted(submitted) != list(range(29)) or sorted(applied) != list(range(29)):
        raise RuntimeError("source journal is not the expected complete 29-action prefix")

    from research.official_pilot.upstream_executor import AppWorldProxy

    AppWorldProxy.allowed_tasks = TASK_ID
    AppWorldProxy.journal_path = RECOVERY_JOURNAL
    AppWorldProxy.journal_trajectory_id = KEY + ":exact-action-replay"
    with AppWorldProxy(task_id=TASK_ID, experiment_name="reduced_v2_exact_score_recovery") as world:
        for index in range(29):
            output = world.execute(submitted[index]["code"])
            output_sha256 = hashlib.sha256(str(output).encode("utf-8")).hexdigest()
            if output_sha256 != applied[index]["output_sha256"]:
                raise RuntimeError(f"native replay diverged at action {index}")
            if bool(world.task_completed()) != bool(applied[index]["completed"]):
                raise RuntimeError(f"completion state diverged at action {index}")
        evaluation = world.evaluate()
        passes, failures = len(evaluation.passes), len(evaluation.failures)
        if passes + failures == 0:
            raise RuntimeError("official scorer returned an empty denominator")
        score = passes / (passes + failures)

    artifact = {
        "task_id": TASK_ID,
        "seed": SEED,
        "trial": TRIAL,
        "arm": ARM,
        "before_score": 0.0,
        "after_score": score,
        "task_completed": bool(applied[28]["completed"]),
        "actions": 29,
        "history": [],
        "memory_sha256": None,
        "reconciled_from_exact_native_action_replay": True,
        "source_journal": str(SOURCE_JOURNAL.relative_to(ROOT)),
        "recovery_journal": str(RECOVERY_JOURNAL.relative_to(ROOT)),
        "source_action_prefix_sha256": digest([
            {"index": i, "code_sha256": submitted[i]["code_sha256"],
             "output_sha256": applied[i]["output_sha256"], "completed": applied[i]["completed"]}
            for i in range(29)
        ]),
        "official_pass_count": passes,
        "official_fail_count": failures,
        "recovery_model_calls": 0,
    }
    ARTIFACT.write_text(json.dumps(artifact, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    artifact_sha256 = hashlib.sha256(ARTIFACT.read_bytes()).hexdigest()
    append(RUN / "completed.jsonl", {"key": KEY, "time_ns": time.time_ns(),
        "state": "reconciled_from_exact_native_action_replay", "artifact": str(ARTIFACT.relative_to(ROOT)),
        "sha256": artifact_sha256, "supersedes_terminal_incomplete_for_analysis": True})
    append(PROGRESS, {"event": "trajectory_reconciled", "stage": "evaluation", "arm": ARM,
        "task_id": TASK_ID, "seed": SEED, "trial": TRIAL, "score": score, "actions": 29,
        "method": "exact_native_action_replay_with_output_hash_verification", "model_calls": 0,
        "artifact_sha256": artifact_sha256})
    print(json.dumps({"score": score, "passes": passes, "failures": failures,
                      "artifact_sha256": artifact_sha256}, sort_keys=True))


if __name__ == "__main__":
    main()
