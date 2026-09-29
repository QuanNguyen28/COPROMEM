"""Path-independent runtime content identities for frozen evaluation runs."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from importlib import metadata
from pathlib import Path
from typing import Any, Mapping


class RuntimeIdentityError(RuntimeError):
    pass


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
    record = {"version": "runtime-content-identity-v1", "entries": entries,
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


def evaluation_runtime_inputs(*, root: Path, reme_source: Path | None = None,
                              appworld_root: Path | None = None, source_commit: str | None = None) -> tuple[dict[str, Path], dict[str, Path], dict[str, str]]:
    """Resolve the explicitly configured, non-secret v6.2 runtime content set.

    Paths are only input locators; ``build_runtime_identity`` records hashes,
    never their machine-specific values.  Missing configured source is a
    pre-dispatch error, not an excuse to substitute a path string.
    """
    root = root.resolve()
    reme_raw = str(reme_source or os.environ.get("COPROMEM_REME_SOURCE", ""))
    appworld_raw = str(appworld_root or os.environ.get("COPROMEM_APPWORLD_ROOT", ""))
    if not reme_raw or not appworld_raw:
        raise RuntimeIdentityError("explicit upstream ReMe and AppWorld source roots are required")
    reme, appworld = Path(reme_raw), Path(appworld_raw)
    if not reme.is_dir() or not appworld.is_dir():
        raise RuntimeIdentityError("explicit upstream ReMe and AppWorld source roots are required")
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
    }
    scorer = appworld / "src/appworld" / "__init__.py"
    if not scorer.is_file():
        scorer = appworld / "appworld" / "__init__.py"
    required["appworld_package_identity"] = scorer
    labels = {"copromem_git_commit": source_commit or os.environ.get("COPROMEM_SOURCE_COMMIT", "unresolved"),
              "python_implementation": platform.python_implementation(), "python_version": platform.python_version(),
              "appworld_distribution_version": metadata.version("appworld") if any(d.metadata.get("Name", "").lower()=="appworld" for d in metadata.distributions()) else "unresolved"}
    if "unresolved" in labels.values():
        raise RuntimeIdentityError("required Git or AppWorld distribution identity is unresolved")
    return required, {"upstream_reme_tree": reme}, labels


def build_evaluation_runtime_identity(*, root: Path, reme_source: Path | None = None,
                                      appworld_root: Path | None = None, source_commit: str | None = None) -> dict[str, Any]:
    content, trees, labels = evaluation_runtime_inputs(root=root, reme_source=reme_source, appworld_root=appworld_root, source_commit=source_commit)
    return build_runtime_identity(content=content, trees=trees, labels=labels)
