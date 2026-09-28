#!/usr/bin/env python3
"""Fail-closed freezer for v5.3's public callable-schema engineering run."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess

from copromem.experiments.reme_copromem.public_tool_schema_registry import build_public_tool_schema_registry, verify_public_tool_schema_registry
from copromem.experiments.reme_copromem.runner import digest, write_json
from scripts.reme_copromem.prepare_tool_schema_v53 import ROOT, _git_env, sha


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--run", type=pathlib.Path, required=True); args = parser.parse_args()
    run = args.run; manifest_path, hash_path = run / "manifest.json", run / "manifest.sha256"
    if manifest_path.exists() or hash_path.exists(): raise RuntimeError("v5.3 manifest is already frozen")
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, env=_git_env()).strip()
    clean = subprocess.run(["git", "diff", "--ignore-space-at-eol", "--exit-code", "HEAD", "--", "src", "scripts"],
                           cwd=ROOT, env=_git_env(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if not clean: raise RuntimeError("commit tracked runtime source before freezing v5.3")
    value = json.loads((run / "template.json").read_text(encoding="utf-8"))
    if value.get("protocol") not in {"v5_3_engineering_012_tool_schema", "v5_3_engineering_013_execution_evidence", "v5_3_engineering_013R_replay_continuation"} or value.get("git_commit") != source:
        raise RuntimeError("v5.3 template source identity mismatch")
    if value.get("arms") != ["no_memory", "copromem_dynamic"] or value["evaluation"].get("expected_trajectories") != 8:
        raise RuntimeError("v5.3 registered arms or trajectory count mismatch")
    registry_path = ROOT / value["evaluation"]["public_registry_relative_path"]
    registry = json.loads(registry_path.read_text(encoding="utf-8")); verify_public_tool_schema_registry(registry)
    runtime = value["evaluation"]["runtime_public_schema"]
    rebuilt = build_public_tool_schema_registry(runtime["openapi_root"], runtime["function_calling_root"])
    if (sha(registry_path) != value["evaluation"]["public_registry_file_sha256"] or
            registry["registry_sha256"] != value["evaluation"]["public_registry_sha256"] or
            rebuilt["registry_sha256"] != registry["registry_sha256"]):
        raise RuntimeError("v5.3 public callable schema freeze mismatch")
    evidence = value["evaluation"].get("execution_evidence")
    if evidence is not None:
        implementation = ROOT / evidence.get("implementation_relative_path", "")
        if (not implementation.is_file() or evidence.get("registry_sha256") != registry["registry_sha256"] or
                sha(implementation) != evidence.get("implementation_sha256")):
            raise RuntimeError("execution-evidence freeze mismatch")
    if value.get("protocol") == "v5_3_engineering_013R_replay_continuation":
        custody = json.loads((run / "custody-audit.json").read_text(encoding="utf-8"))
        if not custody.get("passed"):
            raise RuntimeError("013R custody audit did not prove B was withheld")
    acquisition = pathlib.Path(value["acquisition"]["source_export"])
    rows = json.loads(acquisition.read_text(encoding="utf-8")); rows = rows.get("trajectories", rows)
    if sha(acquisition) != value["acquisition"]["export_sha256"] or len(rows) != 32 or set(row["task_id"] for row in rows) & set(value["evaluation"]["task_ids"]):
        raise RuntimeError("v5.3 task custody/disjointness mismatch")
    initial = json.loads((run / "copromem/initial-state.json").read_text(encoding="utf-8"))
    value["acquisition"]["copromem_initial_state_sha256"] = digest(initial)
    value["dependency_files_sha256"] = {str((ROOT / "pyproject.toml").resolve()): sha(ROOT / "pyproject.toml"), str(registry_path.resolve()): sha(registry_path)}
    if not value["budget"].get("fits_hard_cap") or float(value["budget"]["all_in_usd"]) > 100.0:
        raise RuntimeError("v5.3 all-inclusive budget does not fit the USD 100 cap")
    value["status"] = "frozen_pre_payload"
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    manifest_path.write_bytes(payload); hash_path.write_text(hashlib.sha256(payload).hexdigest() + "\n", encoding="utf-8")
    write_json(run / "freeze-audit.json", {"manifest_sha256": hashlib.sha256(payload).hexdigest(), "source_commit": source,
        "registry_sha256": registry["registry_sha256"], "initial_state_sha256": digest(initial), "provider_calls": 0, "payloads_opened": False})
    print(json.dumps({"manifest_sha256": hashlib.sha256(payload).hexdigest(), "all_in_usd": value["budget"]["all_in_usd"]}, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
