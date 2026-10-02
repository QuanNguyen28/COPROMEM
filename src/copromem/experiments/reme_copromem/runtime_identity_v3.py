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
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable, Mapping

from .runtime_identity import RuntimeIdentityError, _distribution_version, content_hash, resolve_runtime_locators, tree_hash


IDENTITY_VERSION = "runtime-content-identity-v3"
POLICY_RELATIVE_PATH = "research/reme_copromem_fixed_dynamic_review/runtime-content-identity-v3-policy.json"
_CLEAN_REME_TREE_CACHE: dict[tuple[str, str], str] = {}


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
    """Return a checked repository-relative name without resolving every file.

    ``Path.resolve`` performs a filesystem round trip.  On WSL /mnt that made
    clean runtime verification issue one expensive 9P operation per tracked
    file.  Candidates are constructed from the already-resolved repository
    root, so lexical containment is sufficient here.  The executable
    inventory separately rejects Git-mode symlinks before this helper runs.
    """
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise RuntimeIdentityError("runtime identity input escapes the source checkout") from exc
    return relative.as_posix()


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
    # Ask Git for the tracked inventory rather than recursively walking the
    # checkout.  The latter descends through every ignored artifact/cache
    # directory before `_is_ignored` can reject it, which is especially costly
    # for a Windows worktree viewed through WSL /mnt.  A v3 executable
    # inventory is explicitly a tracked-source policy, so Git's inventory is
    # also the more precise authority.
    # Git mode 120000 denotes a symlink.  Do this as one Git metadata read
    # rather than calling ``Path.is_symlink`` for every source file across a
    # WSL-mounted checkout.  Symlinked executable inputs are deliberately
    # unsupported: rejecting them is stricter than resolving potentially
    # escaping paths one at a time.
    tracked_modes: dict[str, str] = {}
    for row in _git(root, ["ls-files", "-s", "-z"]).decode("utf-8").split("\0"):
        if not row:
            continue
        try:
            metadata, relative_text = row.split("\t", 1)
            mode = metadata.split(" ", 1)[0]
        except ValueError as exc:
            raise RuntimeIdentityError("runtime Git inventory is malformed") from exc
        tracked_modes[relative_text] = mode
    tracked = set(tracked_modes)
    paths: set[Path] = set()
    source_roots = [Path(raw_root) for raw_root in policy["source_roots"]]
    for source_root in source_roots:
        if not (root / source_root).is_dir():
            raise RuntimeIdentityError("declared runtime source root is absent")
    for relative_text in tracked:
        if not relative_text:
            continue
        relative = Path(relative_text)
        if relative.suffix not in suffixes or _is_ignored(relative, policy):
            continue
        if any(relative.is_relative_to(source_root) for source_root in source_roots):
            if tracked_modes[relative_text] == "120000":
                raise RuntimeIdentityError("symlinked executable source is unsupported")
            paths.add(root / relative)
    for raw in [*policy["entry_points"], *policy["runtime_configuration_files"]]:
        candidate = root / raw
        if not candidate.is_file():
            raise RuntimeIdentityError("declared runtime entry point or schema is absent")
        if raw in tracked_modes and tracked_modes[raw] == "120000":
            raise RuntimeIdentityError("symlinked executable source is unsupported")
        paths.add(root / raw)
    # The policy intentionally covers *tracked* source.  A newly created
    # runtime-shaped file is audited below as untracked dirt rather than being
    # silently promoted into the executable inventory.
    return sorted((path for path in paths if _repo_relative(root, path) in tracked),
                  key=lambda item: _repo_relative(root, item))


def executable_inventory(root: Path, policy: Mapping[str, Any], *, paths: Iterable[Path] | None = None) -> list[dict[str, Any]]:
    selected = list(paths) if paths is not None else executable_paths(root, policy)
    return [{"path": _repo_relative(root, path), "sha256": _source_sha256(path), "size": len(_source_bytes(path))}
            for path in selected]


def _git(root: Path, args: Iterable[str]) -> bytes:
    """Never inherit a caller's GIT_DIR/GIT_WORK_TREE for another repository."""
    env = {key: value for key, value in os.environ.items() if key not in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"}}
    try:
        pointer = root / ".git"
        # Git-for-Windows accesses an E:/ worktree natively, whereas WSL Git
        # traverses it through the 9P /mnt bridge.  For a Windows-mounted
        # checkout, prefer the installed native executable when available.
        # It receives the same explicit worktree/GIT_DIR arguments and all
        # output is still verified by this identity boundary; POSIX and
        # non-Windows-mounted checkouts retain the ordinary Git path.
        native_git = shutil.which("git.exe") if os.name == "posix" and root.as_posix().startswith("/mnt/") else None
        root_parts = root.parts
        windows_root = (f"{root_parts[2].upper()}:/{'/'.join(root_parts[3:])}"
                        if native_git and len(root_parts) >= 3 else None)
        if native_git and windows_root:
            if pointer.is_file():
                raw = pointer.read_text(encoding="utf-8").strip()
                if raw.lower().startswith("gitdir: ") and len(raw) > 11 and raw[8].isalpha() and raw[9:11] == ":/":
                    env["GIT_DIR"] = raw[8:]
                    env["GIT_WORK_TREE"] = windows_root
                    return subprocess.check_output([native_git, *args], env=env)
            return subprocess.check_output([native_git, "-C", windows_root, *args], env=env)
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


def dirty_state(root: Path, policy: Mapping[str, Any], executable_commit: str,
                *, executable: Iterable[Path] | None = None) -> dict[str, Any]:
    """Compare exactly allowlisted tracked content and relevant untracked files."""
    root = root.resolve()
    changed: list[dict[str, Any]] = []
    selected = list(executable) if executable is not None else executable_paths(root, policy)
    # One ``git diff --name-only`` establishes the clean fast path.  The
    # former implementation spawned ``git show`` once per allowlisted file,
    # which is needlessly expensive for a clean Windows worktree accessed
    # through WSL's /mnt mount.  Runtime identity runs at every
    # dispatch-capable checkpoint, so that I/O pattern could delay a real run
    # by minutes without improving custody.  Only files Git reports changed
    # need their committed blob materialized for the detailed hash record.
    relatives = [_repo_relative(root, path) for path in selected]
    changed_names = set(_git(root, ["diff", "--name-only", "--no-ext-diff", executable_commit,
                                    "--", *relatives]).decode("utf-8").splitlines())
    if not changed_names.issubset(set(relatives)):
        raise RuntimeIdentityError("runtime diff reports a path outside the executable allowlist")
    for path in selected:
        relative = _repo_relative(root, path)
        if relative not in changed_names:
            continue
        actual = _source_bytes(path)
        expected = _git_blob(root, executable_commit, relative).replace(b"\r\n", b"\n")
        if actual != expected:
            changed.append({"path": relative, "expected_sha256": hashlib.sha256(expected).hexdigest(),
                            "observed_sha256": hashlib.sha256(actual).hexdigest(), "size": len(actual)})
    untracked_names = set(_git(root, ["ls-files", "--others", "--exclude-standard", "-z"]).decode("utf-8").split("\0"))
    suffixes = set(policy["untracked_runtime_suffixes"])
    untracked: list[dict[str, Any]] = []
    untracked_roots = [Path(raw_root) for raw_root in policy["untracked_runtime_roots"]]
    for relative_text in untracked_names:
        if not relative_text:
            continue
        relative_path = Path(relative_text)
        if (relative_path.suffix not in suffixes or _is_ignored(relative_path, policy)
                or not any(relative_path.is_relative_to(candidate) for candidate in untracked_roots)):
            continue
        path = root / relative_path
        if not path.is_file():
            raise RuntimeIdentityError("Git reports an unreadable untracked runtime file")
        untracked.append({"path": relative_text, "sha256": _source_sha256(path), "size": len(_source_bytes(path))})
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
    executable_paths_for_identity = executable_paths(root, policy)
    inventory = executable_inventory(root, policy, paths=executable_paths_for_identity)
    executable = component("executable_source", {"policy_sha256": _source_sha256(policy_path or root / POLICY_RELATIVE_PATH),
                                                    "inventory": inventory,
                                                    "inventory_sha256": canonical_hash(inventory),
                                                    "dirty_state": dirty_state(root, policy, executable_commit,
                                                                               executable=executable_paths_for_identity)})
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


def _fast_clean_identity_matches(record: Mapping[str, Any], *, root: Path,
                                 runtime_configuration: Mapping[str, Any],
                                 external_dependencies: Mapping[str, Any],
                                 scientific_inputs: Mapping[str, Any],
                                 policy_path: Path | None = None) -> bool:
    """Validate a clean pinned checkout without rehashing its full source tree.

    Full inventory hashing remains mandatory while freezing a runtime identity
    and whenever a relevant source change is present.  Once the record pins a
    clean commit, however, Git's exact commit plus an allowlisted diff and
    untracked-file check prove that the recorded executable inventory is still
    the committed inventory.  Re-reading and SHA-256 hashing every source
    byte at every dispatch adds no custody information and makes WSL /mnt
    checkouts impractically slow.
    """
    if record.get("version") != IDENTITY_VERSION:
        return False
    try:
        executable_commit = str(record["executable_commit"])
        components = record["components"]
        if not isinstance(components, Mapping):
            return False
        source = components["executable_source"]
        if not isinstance(source, Mapping) or not isinstance(source.get("body"), Mapping):
            return False
        source_body = source["body"]
        policy = load_policy(root, policy_path)
        policy_file = policy_path or (root / POLICY_RELATIVE_PATH)
        if source_body.get("policy_sha256") != _source_sha256(policy_file):
            return False
        actual_commit = _git(root, ["rev-parse", "HEAD"]).decode("utf-8").strip()
        if actual_commit != executable_commit:
            return False
        current_dirty = dirty_state(root, policy, executable_commit)
        if current_dirty["runtime_relevant_dirty"]:
            return False
        if current_dirty != source_body.get("dirty_state"):
            return False
        expected_components = {
            "runtime_configuration": component("runtime_configuration", runtime_configuration),
            "external_dependencies": component("external_dependencies", external_dependencies),
            "scientific_inputs": component("scientific_inputs", scientific_inputs),
        }
        if any(components.get(name) != expected for name, expected in expected_components.items()):
            return False
        aggregate_body = {
            "version": IDENTITY_VERSION,
            "executable_commit": executable_commit,
            "executable_source_sha256": source.get("sha256"),
            "runtime_configuration_sha256": expected_components["runtime_configuration"]["sha256"],
            "external_dependencies_sha256": expected_components["external_dependencies"]["sha256"],
            "scientific_inputs_sha256": expected_components["scientific_inputs"]["sha256"],
        }
        aggregate = component("aggregate_identity", aggregate_body)
        return (components.get("aggregate_identity") == aggregate
                and record.get("runtime_identity_sha256") == aggregate["sha256"])
    except (KeyError, TypeError, RuntimeIdentityError):
        return False


def verify_identity(record: Mapping[str, Any], *, root: Path, runtime_configuration: Mapping[str, Any],
                    external_dependencies: Mapping[str, Any], scientific_inputs: Mapping[str, Any],
                    policy_path: Path | None = None) -> dict[str, Any]:
    if record.get("version") != IDENTITY_VERSION:
        raise RuntimeIdentityError("a v2 identity cannot satisfy a v3 manifest")
    if _fast_clean_identity_matches(record, root=root, runtime_configuration=runtime_configuration,
                                    external_dependencies=external_dependencies, scientific_inputs=scientific_inputs,
                                    policy_path=policy_path):
        # Return a plain mapping, matching the full builder's ownership
        # semantics, without recomputing the already commit-bound inventory.
        return dict(record)
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
    # A clean upstream checkout is fully identified by its Git commit.  Cache
    # the (potentially large) source-tree digest for this Python process after
    # verifying that status is clean; every later identity checkpoint still
    # re-reads commit/status and therefore fails closed on a source change.
    # Dirty ReMe sources are never cached and are hashed on every check.
    cache_key = (str(reme.resolve()), reme_commit)
    if reme_status.strip():
        reme_tree = tree_hash(reme)
    else:
        if cache_key not in _CLEAN_REME_TREE_CACHE:
            _CLEAN_REME_TREE_CACHE[cache_key] = tree_hash(reme)
        reme_tree = _CLEAN_REME_TREE_CACHE[cache_key]
    content = {
        "appworld_package_identity": package / "__init__.py", "appworld_official_evaluator": evaluator,
        "appworld_python_executable": appworld_python, "reme_python_executable": reme_python,
        "upstream_appworld_agent": agent,
    }
    trees = {"appworld_protocol_package": package}
    external = {
        "python_implementation": __import__("platform").python_implementation(), "python_version": __import__("platform").python_version(),
        "appworld_distribution_version": _distribution_version(appworld_python, "appworld"),
        "reme_commit": reme_commit, "reme_dirty": bool(reme_status.strip()),
        "reme_dirty_content_sha256": reme_tree if reme_status.strip() else "clean",
        "content": {name: content_hash(path) for name, path in sorted(content.items())},
        "trees": {**{name: tree_hash(path) for name, path in sorted(trees.items())},
                  "upstream_reme_tree": reme_tree},
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
