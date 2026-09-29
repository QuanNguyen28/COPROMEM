"""Path-independent runtime content identities for frozen evaluation runs."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from typing import Any, Mapping


class RuntimeIdentityError(RuntimeError):
    pass


LOCAL_CONFIG_VERSION = "copromem-runtime-local-v1"
IDENTITY_SCHEMA_VERSION = "runtime-content-identity-v2"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def content_hash(path: Path) -> str:
    if not path.is_file():
        raise RuntimeIdentityError("required runtime content is absent")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hash(root: Path, *, include: tuple[str, ...] = ("*.py", "*.json", "*.toml", "*.lock", "*.txt")) -> str:
    """Hash source content and relative names, deliberately excluding absolute paths."""
    if not root.is_dir():
        raise RuntimeIdentityError("required runtime source tree is absent")
    paths = sorted({path for pattern in include for path in root.rglob(pattern) if path.is_file()})
    if not paths:
        raise RuntimeIdentityError("runtime source tree has no registered source files")
    body = [{"relative": path.relative_to(root).as_posix(), "sha256": content_hash(path)} for path in paths]
    return hashlib.sha256(_canonical(body)).hexdigest()


def build_runtime_identity(*, content: Mapping[str, Path], trees: Mapping[str, Path] | None = None,
                           labels: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Return a portable record that never serializes machine-specific paths."""
    if not content:
        raise RuntimeIdentityError("at least one runtime content identity is required")
    entries = {str(name): {"kind": "file", "sha256": content_hash(Path(path))}
               for name, path in sorted(content.items())}
    for name, path in sorted((trees or {}).items()):
        if name in entries:
            raise RuntimeIdentityError("duplicate runtime identity name")
        entries[str(name)] = {"kind": "tree", "sha256": tree_hash(Path(path))}
    record = {"version": IDENTITY_SCHEMA_VERSION, "entries": entries,
              "labels": dict(sorted((labels or {}).items()))}
    record["runtime_identity_sha256"] = hashlib.sha256(_canonical(record)).hexdigest()
    return record


def verify_runtime_identity(record: Mapping[str, Any], *, content: Mapping[str, Path],
                            trees: Mapping[str, Path] | None = None,
                            labels: Mapping[str, str] | None = None) -> None:
    expected = dict(record)
    observed = build_runtime_identity(content=content, trees=trees, labels=labels)
    if expected != observed:
        raise RuntimeIdentityError("runtime content identity drift")


def _local_runtime_config(root: Path) -> dict[str, str]:
    """Load ignored machine locators; none are included in semantic identity."""
    configured = os.environ.get("COPROMEM_RUNTIME_CONFIG", "")
    path = Path(configured) if configured else root / ".copromem-runtime.json"
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeIdentityError("local runtime configuration is unreadable") from exc
    if not isinstance(value, dict) or value.get("version") != LOCAL_CONFIG_VERSION:
        raise RuntimeIdentityError("local runtime configuration schema is invalid")
    allowed = {"reme_source", "reme_python", "appworld_root", "appworld_python"}
    result: dict[str, str] = {}
    for key, raw in value.items():
        if key == "version":
            continue
        if key not in allowed or not isinstance(raw, str) or not Path(raw).is_absolute():
            raise RuntimeIdentityError("local runtime configuration contains an invalid locator")
        result[key] = raw
    return result


def resolve_runtime_locators(root: Path) -> dict[str, str]:
    """Resolve local roots/interpreters without serializing them into identity."""
    local = _local_runtime_config(root.resolve())
    values = {
        "reme_source": os.environ.get("COPROMEM_REME_SOURCE") or local.get("reme_source", ""),
        "reme_python": os.environ.get("COPROMEM_REME_PYTHON") or local.get("reme_python", ""),
        "appworld_root": os.environ.get("COPROMEM_APPWORLD_ROOT") or local.get("appworld_root", ""),
        "appworld_python": os.environ.get("COPROMEM_APPWORLD_PYTHON") or local.get("appworld_python", ""),
    }
    if not all(values.values()):
        raise RuntimeIdentityError("explicit upstream ReMe, AppWorld, and interpreter locators are required")
    if any(not Path(value).is_absolute() for value in values.values()):
        raise RuntimeIdentityError("runtime locators must be absolute")
    return values


def apply_runtime_locators(root: Path) -> dict[str, str]:
    """Export resolved local locators for maintained service/worker boundaries."""
    locators = resolve_runtime_locators(root)
    os.environ.setdefault("COPROMEM_REME_SOURCE", locators["reme_source"])
    os.environ.setdefault("COPROMEM_REME_PYTHON", locators["reme_python"])
    os.environ.setdefault("COPROMEM_APPWORLD_ROOT", locators["appworld_root"])
    os.environ.setdefault("COPROMEM_APPWORLD_PYTHON", locators["appworld_python"])
    return locators


def _git_identity(root: Path) -> dict[str, str]:
    """Record commit plus deterministic dirty content, never an absolute path."""
    try:
        commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
        status = subprocess.check_output(["git", "-C", str(root), "status", "--porcelain=v1", "--untracked-files=all"], text=True)
        dirty = bool(status.strip())
        # Include content, rather than merely names, when a pinned checkout is dirty.
        diff = subprocess.check_output(["git", "-C", str(root), "diff", "--binary", "HEAD"])
        # The tracked diff plus complete registered tree is sufficient to make
        # dirty source changes content-addressable without serializing locators.
        dirty_hash = hashlib.sha256(diff + _canonical({"tree": tree_hash(root)})).hexdigest() if dirty else "clean"
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeIdentityError("required upstream Git identity is unavailable") from exc
    return {"git_commit": commit, "git_dirty": str(dirty).lower(), "git_dirty_content_sha256": dirty_hash}


def evaluation_runtime_inputs(*, root: Path, reme_source: Path | None = None,
                              appworld_root: Path | None = None, reme_python: Path | None = None,
                              appworld_python: Path | None = None, source_commit: str | None = None) -> tuple[dict[str, Path], dict[str, Path], dict[str, str]]:
    """Resolve the explicitly configured, non-secret v6.2 runtime content set.

    Paths are only input locators; ``build_runtime_identity`` records hashes,
    never their machine-specific values.  Missing configured source is a
    pre-dispatch error, not an excuse to substitute a path string.
    """
    root = root.resolve()
    locators = resolve_runtime_locators(root)
    reme_raw = str(reme_source or locators["reme_source"])
    appworld_raw = str(appworld_root or locators["appworld_root"])
    reme_python_raw = str(reme_python or locators["reme_python"])
    appworld_python_raw = str(appworld_python or locators["appworld_python"])
    reme, appworld = Path(reme_raw), Path(appworld_raw)
    reme_interpreter, appworld_interpreter = Path(reme_python_raw), Path(appworld_python_raw)
    if not reme.is_dir() or not appworld.is_dir() or not reme_interpreter.is_file() or not appworld_interpreter.is_file():
        raise RuntimeIdentityError("explicit runtime roots or interpreters are unavailable")
    required = {
        "evaluation_runner": root / "scripts/run_v61_exploratory_evaluation.py",
        "task_query": root / "src/copromem/experiments/reme_copromem/task_query.py",
        "semantic_lifecycle": root / "src/copromem/experiments/reme_copromem/contrastive_v6_runner.py",
        "evidence_contract": root / "src/copromem/experiments/reme_copromem/evidence_contract.py",
        "copromem_checkpoint": root / "src/copromem/experiments/reme_copromem/copromem_dynamic_checkpoint.py",
        "reme_dynamic_checkpoint": root / "src/copromem/integrations/reme/dynamic_checkpoint.py",
        "reme_fixed_checkpoint": root / "src/copromem/integrations/reme/fixed_checkpoint.py",
        "terminal_reconciliation": root / "src/copromem/experiments/reme_copromem/terminal_reconciliation.py",
        "reme_bridge_service": root / "src/copromem/integrations/reme/corrected_service.py",
        "appworld_worker": root / "src/copromem/benchmarks/appworld/worker.py",
        "public_callable_registry": root / "research/reme_copromem_fixed_dynamic_review/appworld_public_tool_schema_registry_v5_3.json",
        "protocol_decisions": root / "research/reme_copromem_fixed_dynamic_review/V62_PROTOCOL_DECISIONS.md",
        "dependency_lock": root / "pyproject.toml",
        "upstream_appworld_agent": reme / "benchmark/appworld/appworld_react_agent.py",
        "reme_python_executable": reme_interpreter,
        "appworld_python_executable": appworld_interpreter,
    }
    packages = sorted(appworld.glob("venv/lib/python*/site-packages/appworld"))
    if len(packages) != 1:
        raise RuntimeIdentityError("installed AppWorld protocol package is unavailable")
    package = packages[0]
    scorer = package / "evaluator.py"
    if not scorer.is_file():
        raise RuntimeIdentityError("installed official AppWorld evaluator is unavailable")
    required["appworld_package_identity"] = package / "__init__.py"
    required["appworld_official_evaluator"] = scorer
    reme_git = _git_identity(reme)
    try:
        appworld_version = metadata.version("appworld")
    except metadata.PackageNotFoundError:
        # During a real WSL preflight this function runs under the configured
        # AppWorld interpreter.  A host-side result without that distribution
        # must fail closed rather than borrowing an import path.
        appworld_version = "unresolved"
    labels = {"copromem_git_commit": source_commit or os.environ.get("COPROMEM_SOURCE_COMMIT", "unresolved"),
              "python_implementation": platform.python_implementation(), "python_version": platform.python_version(),
              "appworld_distribution_version": appworld_version, **{f"reme_{key}": value for key, value in reme_git.items()}}
    if "unresolved" in labels.values():
        raise RuntimeIdentityError("required Git or AppWorld distribution identity is unresolved")
    return required, {"upstream_reme_tree": reme, "appworld_protocol_package": package}, labels


def build_evaluation_runtime_identity(*, root: Path, reme_source: Path | None = None,
                                      appworld_root: Path | None = None, reme_python: Path | None = None,
                                      appworld_python: Path | None = None, source_commit: str | None = None) -> dict[str, Any]:
    content, trees, labels = evaluation_runtime_inputs(root=root, reme_source=reme_source, appworld_root=appworld_root, reme_python=reme_python, appworld_python=appworld_python, source_commit=source_commit)
    return build_runtime_identity(content=content, trees=trees, labels=labels)
