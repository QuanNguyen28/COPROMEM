"""Build a new CoProMem bank from a frozen acquisition export, then gate it."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from ...integrations.reme.transport import AppendOnlyLedger
from .gate import build_gate
from .runner import append, construct_copromem, digest, raw_acquisition_trajectories, write_json
from .freeze_v5 import ROOT, validate_template


def prepare(template: Path, acquisition: Path, run: Path) -> dict:
    if (run / "manifest.json").exists():
        raise FileExistsError("v5 manifest is already frozen")
    state_path = run / "copromem/initial-state.json"
    gate_path = run / "copromem/acquisition-retrieval-gate.json"
    if state_path.exists() or gate_path.exists():
        raise FileExistsError("v5 acquisition output already exists; use a new run directory")
    changed = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no", "--", "src", "scripts"],
        cwd=ROOT, text=True).strip()
    if changed:
        raise RuntimeError("commit tracked runtime source before v5 acquisition")
    source_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    spec = json.loads(template.read_text(encoding="utf-8"))
    validate_template(spec)
    raw_bytes = acquisition.read_bytes()
    expected_sha = spec["acquisition"].get("source_export_sha256")
    if expected_sha != hashlib.sha256(raw_bytes).hexdigest():
        raise RuntimeError("acquisition export is not pinned by template")
    source = json.loads(raw_bytes)
    rows = source["trajectories"] if isinstance(source, dict) else source
    if len(rows) != spec["acquisition"]["expected_trajectories"]:
        raise RuntimeError("acquisition count differs from template")
    if any(not {"acquisition_identity", "task_id", "instruction", "history", "history_sha256",
                "source_artifact_sha256", "after_score"}.issubset(row) for row in rows):
        raise RuntimeError("acquisition export lacks a required trajectory/provenance field")
    identities = [str(row["acquisition_identity"]) for row in rows]
    if len(set(identities)) != len(identities):
        raise RuntimeError("duplicate acquisition trajectory identity")
    task_instructions: dict[str, str] = {}
    for row in rows:
        identity = str(row["acquisition_identity"])
        match = re.fullmatch(r"(.+)::seed=(\d+)::trajectory=(\d+)", identity)
        if not match or match.group(1) != row["task_id"]:
            raise RuntimeError("acquisition trajectory identity is malformed")
        previous = task_instructions.setdefault(row["task_id"], row["instruction"])
        if previous != row["instruction"] or not isinstance(row["instruction"], str) or not row["instruction"].strip():
            raise RuntimeError("acquisition task has conflicting or empty instructions")
        if digest(row["history"]) != row["history_sha256"]:
            raise RuntimeError("acquisition history digest mismatch")
        instruction = next((message.get("content") for message in row["history"]
                            if message.get("role") == "user"), None)
        if instruction != row["instruction"]:
            raise RuntimeError("acquisition instruction does not match the public history")
    if {row["task_id"] for row in rows} & set(spec["evaluation"]["task_ids"]):
        raise RuntimeError("acquisition and evaluation task IDs overlap")
    run.mkdir(parents=True, exist_ok=True)
    source_record = run / "copromem/acquisition-code.json"
    code_record = {"git_commit": source_commit, "source_export_sha256": hashlib.sha256(raw_bytes).hexdigest()}
    if source_record.exists() and json.loads(source_record.read_text(encoding="utf-8")) != code_record:
        raise RuntimeError("v5 acquisition resume source differs from original code or export")
    if not source_record.exists():
        write_json(source_record, code_record)
    progress = run / "progress.jsonl"
    ledger = AppendOnlyLedger(run / "ledger.jsonl", float(spec["budget"]["ledger_dispatch_cap_usd"]))
    state, bank_hash = construct_copromem(run=run, progress=progress, ledger=ledger,
        api_key="", raw=raw_acquisition_trajectories(rows),
        call_cap=int(spec["budget"]["copromem_decomposition_calls"]))
    gate = build_gate(state, rows)
    write_json(gate_path, gate)
    append(progress, {"event": "v5_warm_start_audit", "bank_sha256": bank_hash,
                      "passed": gate["passed"], "episode_count": gate["episode_count"]})
    return {"bank_sha256": bank_hash, "gate_passed": gate["passed"],
            "episode_count": gate["episode_count"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--acquisition", required=True, type=Path)
    parser.add_argument("--run", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.template, args.acquisition, args.run), sort_keys=True))


if __name__ == "__main__":
    main()
