"""Fail-closed freezer for the v5.2 public-registry engineering manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess

from copromem.experiments.reme_copromem.public_path_registry import verify_public_registry
from copromem.experiments.reme_copromem.runner import digest, write_json


ROOT = pathlib.Path(__file__).resolve().parents[2]


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_env() -> dict[str, str]:
    env = dict(os.environ)
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        env.pop(name, None)
    pointer = ROOT / ".git"
    if pointer.is_file():
        match = re.match(r"gitdir:\s*([A-Za-z]):/(.+)", pointer.read_text(encoding="utf-8").strip())
        if match:
            env["GIT_DIR"] = f"/mnt/{match.group(1).lower()}/{match.group(2)}"
            env["GIT_WORK_TREE"] = str(ROOT)
    return env


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--run", type=pathlib.Path, required=True)
    args = parser.parse_args(); run = args.run
    manifest_path, hash_path = run / "manifest.json", run / "manifest.sha256"
    if manifest_path.exists() or hash_path.exists():
        raise RuntimeError("v5.2 manifest is already frozen")
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, env=git_env()).strip()
    # Native Windows Git records this worktree clean.  WSL may expose only
    # CRLF-at-EOL differences, so compare tracked source while ignoring that
    # transport-only representation difference but no content differences.
    clean = subprocess.run(["git", "diff", "--ignore-space-at-eol", "--exit-code", "HEAD", "--", "src", "scripts"],
                           cwd=ROOT, env=git_env(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if not clean: raise RuntimeError("commit tracked runtime source before freezing v5.2")
    value = json.loads((run / "template.json").read_text(encoding="utf-8"))
    if value.get("protocol") != "v5_2_engineering_011_observable_path" or value.get("git_commit") != source:
        raise RuntimeError("v5.2 template source identity mismatch")
    if value.get("arms") != ["no_memory", "copromem_dynamic"] or value["evaluation"].get("expected_trajectories") != 8:
        raise RuntimeError("v5.2 registered arms or trajectory count mismatch")
    registry_path = ROOT / value["evaluation"]["public_registry_relative_path"]
    registry = json.loads(registry_path.read_text(encoding="utf-8")); verify_public_registry(registry)
    if (sha(registry_path) != value["evaluation"]["public_registry_file_sha256"]
            or registry["registry_sha256"] != value["evaluation"]["public_registry_sha256"]):
        raise RuntimeError("v5.2 frozen registry mismatch")
    acquisition = pathlib.Path(value["acquisition"]["source_export"])
    if sha(acquisition) != value["acquisition"]["export_sha256"]:
        raise RuntimeError("v5.2 acquisition export mismatch")
    rows = json.loads(acquisition.read_text(encoding="utf-8")); rows = rows.get("trajectories", rows)
    if len(rows) != 32 or set(row["task_id"] for row in rows) & set(value["evaluation"]["task_ids"]):
        raise RuntimeError("v5.2 task custody/disjointness mismatch")
    initial = json.loads((run / "copromem/initial-state.json").read_text(encoding="utf-8"))
    value["acquisition"]["copromem_initial_state_sha256"] = digest(initial)
    value["dependency_files_sha256"] = {str((ROOT / "pyproject.toml").resolve()): sha(ROOT / "pyproject.toml"),
                                          str(registry_path.resolve()): sha(registry_path)}
    budget = value["budget"]
    if not budget.get("fits_hard_cap") or float(budget["all_in_usd"]) > 100.0:
        raise RuntimeError("v5.2 all-inclusive budget does not fit the USD 100 cap")
    value["status"] = "frozen_pre_payload"
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    manifest_path.write_bytes(payload); hash_path.write_text(hashlib.sha256(payload).hexdigest() + "\n", encoding="utf-8")
    write_json(run / "freeze-audit.json", {"manifest_sha256": hashlib.sha256(payload).hexdigest(), "source_commit": source,
        "registry_sha256": registry["registry_sha256"], "initial_state_sha256": digest(initial),
        "provider_calls": 0, "payloads_opened": False})
    print(json.dumps({"manifest_sha256": hashlib.sha256(payload).hexdigest(), "all_in_usd": budget["all_in_usd"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
