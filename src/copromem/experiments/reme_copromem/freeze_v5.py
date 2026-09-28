"""Freeze a new v5 run manifest after acquisition and offline retrieval gating."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
from ...learning import ActionObservation, LearningCore


ROOT = pathlib.Path(__file__).resolve().parents[4]


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_template(value: dict) -> None:
    if value.get("protocol") != "continuous_copromem_v5":
        raise ValueError("template must declare continuous_copromem_v5")
    if value.get("arms") != ["no_memory", "official_upstream_reme_fixed",
                              "official_upstream_reme_dynamic", "copromem_dynamic"]:
        raise ValueError("continuous v5 requires exactly four registered arms")
    evaluation = value.get("evaluation", {})
    descriptors = evaluation.get("descriptors", {})
    if set(descriptors) != set(evaluation.get("task_ids", ())):
        raise ValueError("every evaluation task needs a public descriptor")
    expectations = evaluation.get("expected_initial_compatibility", {})
    if not isinstance(expectations, dict) or not set(expectations) <= set(descriptors):
        raise ValueError("descriptor compatibility expectations must name evaluation tasks")
    if any(value not in {"compatible", "unknown"} for value in expectations.values()):
        raise ValueError("descriptor compatibility expectation must be compatible or unknown")
    for raw in descriptors.values():
        events = tuple(ActionObservation(**item) for item in raw)
        if (not LearningCore.signature(events)
                or any(item.check or item.parameters or not item.observed for item in events)):
            raise ValueError("descriptor must contain only pre-execution structure")


def freeze(template: pathlib.Path, acquisition: pathlib.Path, run: pathlib.Path,
           dependency_files: list[pathlib.Path]) -> pathlib.Path:
    if (run / "manifest.json").exists() or (run / "manifest.sha256").exists():
        raise FileExistsError("frozen v5 manifest already exists")
    status = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no", "--", "src", "scripts"],
        cwd=ROOT, text=True).strip()
    if status:
        raise RuntimeError("commit tracked runtime source before freezing v5")
    value = json.loads(template.read_text(encoding="utf-8"))
    validate_template(value)
    state_path, gate_path = run / "copromem/initial-state.json", run / "copromem/acquisition-retrieval-gate.json"
    code_record = json.loads((run / "copromem/acquisition-code.json").read_text(encoding="utf-8"))
    state = json.loads(state_path.read_text(encoding="utf-8"))
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    canonical = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    bank_hash = hashlib.sha256(canonical).hexdigest()
    if not gate.get("passed") or gate.get("bank_sha256") != bank_hash:
        raise RuntimeError("v5 retrieval gate has not passed for the frozen bank")
    rows = json.loads(acquisition.read_text(encoding="utf-8"))
    rows = rows["trajectories"] if isinstance(rows, dict) else rows
    if len(rows) != value["acquisition"]["expected_trajectories"]:
        raise RuntimeError("acquisition count differs from template")
    if {row["task_id"] for row in rows} & set(value["evaluation"]["task_ids"]):
        raise RuntimeError("acquisition and evaluation IDs overlap")
    value["acquisition"].update(export_sha256=sha(acquisition), copromem_bank_sha256=bank_hash,
                                retrieval_gate_sha256=sha(gate_path))
    value["git_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if code_record != {"git_commit": value["git_commit"], "source_export_sha256": sha(acquisition)}:
        raise RuntimeError("bank construction code or export differs from frozen v5 inputs")
    if not dependency_files:
        raise ValueError("at least one external dependency file must be pinned")
    value["dependency_files_sha256"] = {str(path.resolve()): sha(path) for path in dependency_files}
    value["status"] = "frozen_pre_payload"
    run.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n"
    (run / "manifest.json").write_bytes(payload)
    (run / "manifest.sha256").write_text(hashlib.sha256(payload).hexdigest() + "\n", encoding="utf-8")
    return run / "manifest.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", required=True, type=pathlib.Path)
    parser.add_argument("--acquisition", required=True, type=pathlib.Path)
    parser.add_argument("--run", required=True, type=pathlib.Path)
    parser.add_argument("--dependency-file", action="append", required=True, type=pathlib.Path)
    args = parser.parse_args()
    print(freeze(args.template, args.acquisition, args.run, args.dependency_file))


if __name__ == "__main__":
    main()
