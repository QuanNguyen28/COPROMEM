"""Portable, content-addressed runtime identities for v6.2.1 successors.

V2 recorded a useful broad runtime fingerprint, but its Git dirty state was
worktree-wide.  This module deliberately has a smaller custody boundary: only
the explicit executable policy can affect a v3 runtime identity.  It performs
no network, provider, AppWorld, or service operation.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Iterable, Mapping

from .runtime_identity import RuntimeIdentityError, _distribution_version, content_hash, resolve_runtime_locators, tree_hash


IDENTITY_VERSION = "runtime-content-identity-v3"
POLICY_RELATIVE_PATH = "research/reme_copromem_fixed_dynamic_review/runtime-content-identity-v3-policy.json"


def canonical_bytes(value: Any) -> bytes:
    """Canonical JSON bytes; persisted callers append exactly one newline."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def write_canonical_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value) + b"\n")


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise RuntimeIdentityError(f"required runtime content is absent: {path.name}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_bytes(path: Path) -> bytes:
    """Canonical tracked-source bytes across Git's Windows CRLF checkout filter.

    The policy is limited to textual Python/configuration formats.  Git stores
    their canonical LF content while a clean Windows checkout may materialize
    CRLF.  Comparing the materialized bytes would incorrectly call a clean
    checkout dirty, so v3 compares the Git-equivalent logical bytes.  This is
    deliberately not used for banks, journals, or other scientific artifacts.
    """
    return path.read_bytes().replace(b"\r\n", b"\n")


def _source_sha256(path: Path) -> str:
    if not path.is_file():
        raise RuntimeIdentityError(f"required runtime content is absent: {path.name}")
    return hashlib.sha256(_source_bytes(path)).hexdigest()


def _repo_relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise RuntimeIdentityError("runtime identity input escapes the source checkout") from exc


def load_policy(root: Path, policy_path: Path | None = None) -> dict[str, Any]:
    path = policy_path or (root / POLICY_RELATIVE_PATH)
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeIdentityError("runtime v3 policy is unreadable") from exc
    required = {"version", "source_roots", "source_suffixes", "entry_points", "runtime_configuration_files", "untracked_runtime_roots", "ignored_directory_names", "untracked_runtime_suffixes"}
    if not isinstance(policy, dict) or not required <= set(policy):
        raise RuntimeIdentityError("runtime v3 policy schema is invalid")
    if policy["version"] != "runtime-content-identity-v3-policy-1":
        raise RuntimeIdentityError("runtime v3 policy version is unsupported")
    for field in required - {"version"}:
        if not isinstance(policy[field], list) or not all(isinstance(item, str) and item for item in policy[field]):
            raise RuntimeIdentityError("runtime v3 policy contains an invalid list")
    return policy


def _is_ignored(relative: Path, policy: Mapping[str, Any]) -> bool:
    return any(part in set(policy["ignored_directory_names"]) for part in relative.parts)


def executable_paths(root: Path, policy: Mapping[str, Any]) -> list[Path]:
    """Return the exact sorted allowlist, never source-tree enumeration order."""
    root = root.resolve()
    suffixes = set(policy["source_suffixes"])
    paths: set[Path] = set()
    for raw_root in policy["source_roots"]:
        directory = root / raw_root
        if not directory.is_dir():
            raise RuntimeIdentityError("declared runtime source root is absent")
        for candidate in directory.rglob("*"):
            if candidate.is_file() and candidate.suffix in suffixes and not _is_ignored(candidate.relative_to(root), policy):
                paths.add(candidate.resolve())
    for raw in [*policy["entry_points"], *policy["runtime_configuration_files"]]:
        candidate = (root / raw).resolve()
        if not candidate.is_file():
            raise RuntimeIdentityError("declared runtime entry point or schema is absent")
        paths.add(candidate)
    # The policy intentionally covers *tracked* source.  A newly created
    # runtime-shaped file is audited below as untracked dirt rather than being
    # silently promoted into the executable inventory.
    tracked = set(_git(root, ["ls-files", "-z"]).decode("utf-8").split("\0"))
    return sorted((path for path in paths if _repo_relative(root, path) in tracked),
                  key=lambda item: _repo_relative(root, item))


def executable_inventory(root: Path, policy: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [{"path": _repo_relative(root, path), "sha256": _source_sha256(path), "size": len(_source_bytes(path))}
            for path in executable_paths(root, policy)]


def _git(root: Path, args: Iterable[str]) -> bytes:
    """Never inherit a caller's GIT_DIR/GIT_WORK_TREE for another repository."""
    env = {key: value for key, value in os.environ.items() if key not in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"}}
    try:
        pointer = root / ".git"
        # Git-for-Windows follows the linked-worktree pointer directly.  WSL
        # Git needs the Windows pointer translated, but only for this exact
        # checkout; never inherit an unrelated caller's GIT_DIR.
        if os.name == "posix" and pointer.is_file():
            raw = pointer.read_text(encoding="utf-8").strip()
            if raw.lower().startswith("gitdir: ") and len(raw) > 11 and raw[8].isalpha() and raw[9:11] == ":/":
                drive, tail = raw[8], raw[11:]
                env["GIT_DIR"] = f"/mnt/{drive.lower()}/{tail}"
                env["GIT_WORK_TREE"] = str(root)
                return subprocess.check_output(["git", *args], env=env)
        return subprocess.check_output(["git", "-C", str(root), *args], env=env)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeIdentityError("runtime v3 requires a readable Git checkout") from exc


def _git_blob(root: Path, commit: str, relative: str) -> bytes:
    try:
        return _git(root, ["show", f"{commit}:{relative}"])
    except RuntimeIdentityError as exc:
        raise RuntimeIdentityError("declared executable commit lacks an allowlisted file") from exc


def dirty_state(root: Path, policy: Mapping[str, Any], executable_commit: str) -> dict[str, Any]:
    """Compare exactly allowlisted tracked content and relevant untracked files."""
    root = root.resolve()
    changed: list[dict[str, Any]] = []
    for path in executable_paths(root, policy):
        relative = _repo_relative(root, path)
        actual = _source_bytes(path)
        expected = _git_blob(root, executable_commit, relative).replace(b"\r\n", b"\n")
        if actual != expected:
            changed.append({"path": relative, "expected_sha256": hashlib.sha256(expected).hexdigest(),
                            "observed_sha256": hashlib.sha256(actual).hexdigest(), "size": len(actual)})
    tracked = set(_git(root, ["ls-files", "-z"]).decode("utf-8").split("\0"))
    suffixes = set(policy["untracked_runtime_suffixes"])
    untracked: list[dict[str, Any]] = []
    for raw_root in policy["untracked_runtime_roots"]:
        directory = root / raw_root
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or path.suffix not in suffixes:
                continue
            relative = _repo_relative(root, path)
            if _is_ignored(Path(relative), policy) or relative in tracked:
                continue
            untracked.append({"path": relative, "sha256": _source_sha256(path), "size": len(_source_bytes(path))})
    changed.sort(key=lambda item: item["path"]); untracked.sort(key=lambda item: item["path"])
    payload = {"tracked_changed": changed, "untracked_runtime": untracked}
    return {"runtime_relevant_dirty": bool(changed or untracked), **payload,
            "dirty_content_sha256": canonical_hash(payload)}


def _normal(value: Mapping[str, Any], required: set[str] | None = None) -> dict[str, Any]:
    if required and not required <= set(value):
        raise RuntimeIdentityError("runtime v3 component is missing required semantic values")
    # JSON roundtrip ensures mapping implementations, paths, and ordering cannot leak in.
    try:
        return json.loads(canonical_bytes(dict(value)).decode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise RuntimeIdentityError("runtime v3 component is not canonical JSON") from exc


def component(name: str, body: Mapping[str, Any]) -> dict[str, Any]:
    clean = _normal(body)
    return {"name": name, "body": clean, "sha256": canonical_hash(clean)}


def build_identity(*, root: Path, executable_commit: str, runtime_configuration: Mapping[str, Any],
                   external_dependencies: Mapping[str, Any], scientific_inputs: Mapping[str, Any],
                   policy_path: Path | None = None) -> dict[str, Any]:
    """Build a fully portable v3 record from already-public semantic inputs."""
    root = root.resolve(); policy = load_policy(root, policy_path)
    actual_commit = _git(root, ["rev-parse", "HEAD"]).decode("utf-8").strip()
    if actual_commit != executable_commit:
        raise RuntimeIdentityError("declared executable commit differs from runtime checkout")
    inventory = executable_inventory(root, policy)
    executable = component("executable_source", {"policy_sha256": _source_sha256(policy_path or root / POLICY_RELATIVE_PATH),
                                                    "inventory": inventory,
                                                    "inventory_sha256": canonical_hash(inventory),
                                                    "dirty_state": dirty_state(root, policy, executable_commit)})
    configuration = component("runtime_configuration", runtime_configuration)
    dependencies = component("external_dependencies", external_dependencies)
    inputs = component("scientific_inputs", scientific_inputs)
    aggregate_body = {"version": IDENTITY_VERSION, "executable_commit": executable_commit,
                      "executable_source_sha256": executable["sha256"],
                      "runtime_configuration_sha256": configuration["sha256"],
                      "external_dependencies_sha256": dependencies["sha256"],
                      "scientific_inputs_sha256": inputs["sha256"]}
    aggregate = component("aggregate_identity", aggregate_body)
    return {"version": IDENTITY_VERSION, "executable_commit": executable_commit,
            "components": {"executable_source": executable, "runtime_configuration": configuration,
                           "external_dependencies": dependencies, "scientific_inputs": inputs,
                           "aggregate_identity": aggregate},
            "runtime_identity_sha256": aggregate["sha256"]}


def verify_identity(record: Mapping[str, Any], *, root: Path, runtime_configuration: Mapping[str, Any],
                    external_dependencies: Mapping[str, Any], scientific_inputs: Mapping[str, Any],
                    policy_path: Path | None = None) -> dict[str, Any]:
    if record.get("version") != IDENTITY_VERSION:
        raise RuntimeIdentityError("a v2 identity cannot satisfy a v3 manifest")
    observed = build_identity(root=root, executable_commit=str(record.get("executable_commit", "")),
                              runtime_configuration=runtime_configuration,
                              external_dependencies=external_dependencies,
                              scientific_inputs=scientific_inputs, policy_path=policy_path)
    if dict(record) != observed:
        raise RuntimeIdentityError("runtime v3 content identity drift")
    return observed


def verify_manifest_identity(manifest: Mapping[str, Any], record: Mapping[str, Any], *, root: Path,
                             runtime_configuration: Mapping[str, Any], external_dependencies: Mapping[str, Any],
                             scientific_inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Manifest/start/restart/pre-task/terminal common v3 verifier."""
    if manifest.get("runtime_identity_version") != IDENTITY_VERSION:
        raise RuntimeIdentityError("manifest does not require runtime-content-identity-v3")
    observed = verify_identity(record, root=root, runtime_configuration=runtime_configuration,
                               external_dependencies=external_dependencies, scientific_inputs=scientific_inputs)
    if manifest.get("runtime_identity_sha256") != observed["runtime_identity_sha256"]:
        raise RuntimeIdentityError("manifest-bound v3 runtime identity mismatch")
    return observed


def evaluation_v3_inputs(*, root: Path, manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Derive the non-secret v3 component inputs used by the maintained runner.

    This is the one production bridge from a frozen engineering manifest to
    the five v3 components.  It reads metadata and installed-file identities
    only; it never starts a service or contacts a provider.
    """
    execution = manifest.get("execution"); evaluation = manifest.get("evaluation"); banks = manifest.get("banks")
    policy = manifest.get("method_policy")
    if not all(isinstance(value, Mapping) for value in (execution, evaluation, banks, policy)):
        raise RuntimeIdentityError("v3 manifest lacks semantic identity inputs")
    registry_path = root / "research/reme_copromem_fixed_dynamic_review/appworld_public_tool_schema_registry_v5_3.json"
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry_sha256 = str(registry["registry_sha256"])
        method_policy_sha256 = str(policy["policy_sha256"])
        allocation_sha256 = str(evaluation["allocation_audit_sha256"])
        task_ids = list(evaluation["task_ids"]); seeds = list(evaluation["seeds"])
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeIdentityError("v3 manifest scientific inputs are invalid") from exc
    configuration = {
        "model": execution.get("model"), "provider_route": execution.get("provider_only"),
        "temperature": execution.get("temperature"),
        "limits": {name: execution.get(name) for name in ("max_actions", "completion_token_ceiling", "context_token_ceiling")},
        "arms": list(manifest.get("arms", ())), "retrieval_policy_sha256": method_policy_sha256,
        "prompt_tool_interface": "v6.2.1-maintained", "scorer_contract": "official-appworld",
        "ledger_policy": "append-only-hard-cap", "storage_policy": dict(manifest.get("storage_policy", {})),
        "callable_registry_sha256": registry_sha256,
    }
    locators = resolve_runtime_locators(root)
    reme = Path(locators["reme_source"]); appworld = Path(locators["appworld_root"])
    reme_python = Path(locators["reme_python"]); appworld_python = Path(locators["appworld_python"])
    if not reme.is_dir() or not appworld.is_dir() or not reme_python.is_file() or not appworld_python.is_file():
        raise RuntimeIdentityError("v3 external dependency locators are unavailable")
    packages = sorted(appworld.glob("venv/lib/python*/site-packages/appworld"))
    if len(packages) != 1:
        raise RuntimeIdentityError("v3 installed AppWorld package is unavailable")
    package = packages[0]; evaluator = package / "evaluator.py"; agent = reme / "benchmark/appworld/appworld_react_agent.py"
    if not evaluator.is_file() or not agent.is_file():
        raise RuntimeIdentityError("v3 external protocol source is unavailable")
    reme_commit = _git(reme, ["rev-parse", "HEAD"]).decode("utf-8").strip()
    reme_status = _git(reme, ["status", "--porcelain=v1", "--untracked-files=no"]).decode("utf-8")
    reme_tree = tree_hash(reme)
    content = {
        "appworld_package_identity": package / "__init__.py", "appworld_official_evaluator": evaluator,
        "appworld_python_executable": appworld_python, "reme_python_executable": reme_python,
        "upstream_appworld_agent": agent,
    }
    trees = {"appworld_protocol_package": package, "upstream_reme_tree": reme}
    external = {
        "python_implementation": __import__("platform").python_implementation(), "python_version": __import__("platform").python_version(),
        "appworld_distribution_version": _distribution_version(appworld_python, "appworld"),
        "reme_commit": reme_commit, "reme_dirty": bool(reme_status.strip()),
        "reme_dirty_content_sha256": reme_tree if reme_status.strip() else "clean",
        "content": {name: content_hash(path) for name, path in sorted(content.items())},
        "trees": {name: tree_hash(path) for name, path in sorted(trees.items())},
    }
    scientific = {
        "copromem_initial_bank_sha256": banks.get("copromem_sha256"), "reme_initial_bank_sha256": banks.get("reme_shared_sha256"),
        "callable_registry_sha256": registry_sha256, "allocation_sha256": allocation_sha256,
        "method_policy_sha256": method_policy_sha256,
        "task_trial_identity_sha256": canonical_hash({"task_ids": task_ids, "seeds": seeds}),
    }
    return {"runtime_configuration": configuration, "external_dependencies": external, "scientific_inputs": scientific}


def build_evaluation_identity_v3(*, root: Path, manifest: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    inputs = evaluation_v3_inputs(root=root, manifest=manifest)
    record = build_identity(root=root, executable_commit=str(manifest.get("git_commit", "")), **inputs)
    return record, inputs
