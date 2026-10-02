#!/usr/bin/env python3
"""Small exposed integration pilot: CoProMem v6.2.2, ReMe, ReasoningBank.

All arms share the maintained AppWorld executor, official scorer, model route,
task order, and stochastic trial labels.  ReasoningBank is evaluated from one
frozen, previously engineering-validated bank and is non-mutating here, which
makes it comparable to the two fixed-bank arms.  Dynamic ReMe and CoProMem
remain registered as diagnostic adaptation arms.  This is integration evidence,
not a confirmatory efficacy experiment.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping

from scripts import run_v622_semantic_spine_engineering as v622
from scripts import run_v61_exploratory_evaluation as base
from copromem.experiments.reme_copromem.runner import write_json
from copromem.experiments.reme_copromem.runtime_identity_v3 import build_evaluation_identity_v3
from copromem.integrations.reasoning_bank.appworld import ReasoningBank
from copromem.integrations.reasoning_bank.dynamic_runtime import ReasoningBankDynamicRuntime
from copromem.integrations.reasoning_bank.lifecycle import ReasoningBankLifecycle
from copromem.integrations.reasoning_bank.retrieval_provenance import ContentAddressedStore, verify
from copromem.integrations.reasoning_bank.shared_embedding import (
    DIMENSIONS, ENCODING_FORMAT, MODEL as EMBEDDING_MODEL, PROVIDER as EMBEDDING_PROVIDER,
    SharedAzureOpenRouterEmbedder,
)
from copromem.integrations.reme.transport import verify_locked_chat_route_available
from copromem.integrations.reme.transport import PROVIDER as CHAT_PROVIDER


PROTOCOL = "v6_2_2_parallel_baseline_pilot"
RUN_NAME = "v6_2_2_parallel_baseline_pilot"
REASONINGBANK_ARM = "reasoningbank_dynamic"  # persisted compatibility ID; report label is ReasoningBank
ARMS = ["no_memory", "official_upstream_reme_fixed", "official_upstream_reme_dynamic",
        REASONINGBANK_ARM, "copromem_v6_2_2_fixed", "copromem_v6_2_2_dynamic"]
ALLOCATION_NAME = "allocation-audit-v622.json"


def _external(path: str) -> Path:
    return Path("/mnt/e" + path[2:].replace("\\", "/")) if os.name == "posix" else Path(path)


REVIEW = _external(r"E:\Project\AAMAS\COPROMEM-review")
RB_RUN = _external(r"E:\Project\AAMAS\reasoningbank-appworld-artifacts\reasoningbank_appworld_engineering_016_recovery")
RB_BANK = RB_RUN / "reasoningbank-dynamic-checkpoints/snapshots/0006.json"


def _declared_protocol(run: Path) -> str:
    """Bind the manifest label to the versioned frozen protocol record."""
    try:
        value = json.loads((run / "engineering-protocol.json").read_text(encoding="utf-8"))["version"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("parallel pilot lacks a readable versioned engineering protocol") from exc
    if not isinstance(value, str) or not value.startswith("v6.2.2-parallel-baseline-pilot-protocol-"):
        raise RuntimeError("parallel pilot protocol version is invalid")
    return value


def _configure(run: Path) -> None:
    # The shared ReMe construction and acquisition banks are immutable E-backed
    # artifacts, not copied into each source checkout.
    base.SOURCE = REVIEW / "artifacts/research/official_reme_copromem_pilot/v6_shared_acquisition_001"
    base.CONSTRUCTION = REVIEW / "artifacts/research/official_reme_copromem_pilot/v6_1_exploratory_diagnostic_construction_003"
    v622._configure(run)
    base.PROTOCOL = _declared_protocol(run)
    base.ARMS = list(ARMS)
    base.CALL_LIMITS = {"executor": 1080, "reme_lifecycle": 128, "reme_embedding": 512,
                        "copromem_decomposition": 0}
    base.EXTRA_RUNTIME_FACTORY = _runtime_factory
    base.EXTRA_ARM_KWARGS = _arm_kwargs
    base.EXTRA_EXISTING_VALIDATOR = _existing_validator
    base.EXTRA_TERMINAL_CHECK = _terminal_check


def _rb_manifest_record(run: Path) -> Mapping[str, Any]:
    audit = json.loads((run / ALLOCATION_NAME).read_text(encoding="utf-8"))
    record = audit.get("reasoningbank_bank")
    if not isinstance(record, Mapping):
        raise RuntimeError("parallel pilot lacks frozen ReasoningBank bank identity")
    if Path(str(record.get("path") or "")) != RB_BANK or not RB_BANK.is_file():
        raise RuntimeError("ReasoningBank bank locator differs from frozen pilot identity")
    if base.file_sha(RB_BANK) != record.get("file_sha256"):
        raise RuntimeError("ReasoningBank bank bytes differ from frozen pilot identity")
    bank = ReasoningBank.restore(json.loads(RB_BANK.read_text(encoding="utf-8")))
    if bank.state()["semantic_state_sha256"] != record.get("semantic_state_sha256"):
        raise RuntimeError("ReasoningBank semantic state differs from frozen pilot identity")
    return record


def _runtime_factory(run: Path, manifest: Mapping[str, Any], ledger: Any, api_key: str,
                     registry: Mapping[str, Any]) -> dict[str, Any]:
    record = _rb_manifest_record(run)
    initial = ReasoningBank.restore(json.loads(RB_BANK.read_text(encoding="utf-8")))
    # Judge/extractor are deliberately unavailable: this arm is frozen-bank
    # retrieval only. Any accidental update attempt fails before a provider call.
    def forbidden(*_args: Any, **_kwargs: Any):
        raise RuntimeError("fixed ReasoningBank pilot arm cannot update its bank")
    lifecycle = ReasoningBankLifecycle(
        bank=initial,
        embedder=SharedAzureOpenRouterEmbedder(api_key=api_key, ledger=ledger, progress=run / "progress.jsonl"),
        judge=forbidden,
        extractor=forbidden,
    )
    runtime_record = json.loads((run / "runtime-identity.json").read_text(encoding="utf-8"))
    runtime = ReasoningBankDynamicRuntime(
        lifecycle=lifecycle, initial_bank=initial, checkpoints=None, run_root=run,
        registry_sha256=str(registry["registry_sha256"]), manifest_sha256=base.file_sha(run / "manifest.json"),
        runtime_identity_sha256=str(runtime_record["runtime_identity_sha256"]),
        runtime_identity_record_sha256=base.file_sha(run / "runtime-identity.json"),
        embedding_identity={"model": EMBEDDING_MODEL, "provider": EMBEDDING_PROVIDER,
                            "dimensions": DIMENSIONS, "encoding_format": ENCODING_FORMAT},
    )
    return {"runtime": runtime, "initial_sha256": record["semantic_state_sha256"]}


def _identity(run: Path, manifest: Mapping[str, Any], task: str, trial: int, seed: int) -> dict[str, Any]:
    runtime_record = json.loads((run / "runtime-identity.json").read_text(encoding="utf-8"))
    return {"trajectory_id": f"evaluation:{REASONINGBANK_ARM}:{task}:trial={trial}:seed={seed}",
            "task_id": task, "arm": REASONINGBANK_ARM, "trial_id": trial, "seed": seed,
            "benchmark": "appworld", "manifest_sha256": base.file_sha(run / "manifest.json"),
            "runtime_identity_sha256": runtime_record["runtime_identity_sha256"],
            "registry_sha256": json.loads(base.REG.read_text(encoding="utf-8"))["registry_sha256"]}


def _retrieval_path(run: Path, task: str, trial: int) -> Path:
    return run / "retrievals" / task / f"{REASONINGBANK_ARM}-{trial}.json"


def _arm_kwargs(context: Mapping[str, Any] | None, run: Path, manifest: Mapping[str, Any], arm: str,
                task: str, trial: int, seed: int, _artifact: Path) -> dict[str, Any]:
    if arm != REASONINGBANK_ARM:
        return {}
    if context is None:
        raise RuntimeError("ReasoningBank fixed runtime is absent")
    runtime = context["runtime"]; path = _retrieval_path(run, task, trial)
    identity = _identity(run, manifest, task, trial, seed)
    return {"memory_for_instruction": runtime.retrieval_callback(path, identity=identity),
            "pre_dispatch_binding": runtime.prompt_binding_callback(path, identity=identity)}


def _verify_one(context: Mapping[str, Any], run: Path, manifest: Mapping[str, Any],
                task: str, trial: int, seed: int, artifact: Path) -> None:
    path = _retrieval_path(run, task, trial)
    value = verify(path=path, store=ContentAddressedStore(run / "reasoningbank-retrieval-objects"),
                   expected_bank_sha256=str(context["initial_sha256"]), require_prompt_binding=True)
    if value["identity"] != _identity(run, manifest, task, trial, seed):
        raise RuntimeError("ReasoningBank retrieval identity differs from frozen schedule")
    row = json.loads(artifact.read_text(encoding="utf-8")); binding = value.get("prompt_binding") or {}
    if row.get("initial_prompt_messages_sha256") != binding.get("initial_prompt_messages_sha256"):
        raise RuntimeError("ReasoningBank artifact differs from sealed model-visible prompt")


def _existing_validator(context: Mapping[str, Any] | None, run: Path, manifest: Mapping[str, Any], arm: str,
                        task: str, trial: int, seed: int, artifact: Path, _result: Mapping[str, Any]) -> None:
    if arm == REASONINGBANK_ARM:
        if context is None: raise RuntimeError("ReasoningBank fixed runtime is absent")
        _verify_one(context, run, manifest, task, trial, seed, artifact)


_ACTIVE_CONTEXT: Mapping[str, Any] | None = None


def _terminal_check(run: Path, manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    if _ACTIVE_CONTEXT is None:
        raise RuntimeError("ReasoningBank terminal context is absent")
    count = 0
    for task in manifest["evaluation"]["task_ids"]:
        for trial, seed in enumerate(manifest["evaluation"]["seeds"], 1):
            artifact = run / "artifacts" / task / REASONINGBANK_ARM / f"trial-{trial}.json"
            _verify_one(_ACTIVE_CONTEXT, run, manifest, task, trial, seed, artifact); count += 1
    if _ACTIVE_CONTEXT["runtime"].lifecycle.bank.state()["semantic_state_sha256"] != _ACTIVE_CONTEXT["initial_sha256"]:
        raise RuntimeError("ReasoningBank fixed bank mutated")
    return {"valid": True, "retrieval_count": count, "fixed_bank_sha256": _ACTIVE_CONTEXT["initial_sha256"]}


def _capturing_factory(*args: Any, **kwargs: Any) -> Mapping[str, Any]:
    global _ACTIVE_CONTEXT
    _ACTIVE_CONTEXT = _runtime_factory(*args, **kwargs)
    return _ACTIVE_CONTEXT


def prepare(run: Path) -> None:
    _configure(run); base.EXTRA_RUNTIME_FACTORY = _capturing_factory
    v622.prepare(run)
    template_path = run / "template.json"; template = json.loads(template_path.read_text(encoding="utf-8"))
    allocation = json.loads((run / ALLOCATION_NAME).read_text(encoding="utf-8"))
    rb = _rb_manifest_record(run)
    template["protocol"] = _declared_protocol(run); template["arms"] = list(ARMS)
    template["execution"]["provider_only"] = CHAT_PROVIDER
    template["evaluation"]["expected_trajectories"] = len(template["evaluation"]["task_ids"]) * len(template["evaluation"]["seeds"]) * len(ARMS)
    template["banks"]["reasoningbank_sha256"] = rb["semantic_state_sha256"]
    template["method"]["reasoningbank"] = "official top-1/no-abstention retrieval from a frozen engineering-validated bank"
    template["method"]["comparison_design"] = "shared executor/scorer/model/task/seed; exposed integration diagnostic"
    template["method"]["provider_amendment"] = (
        "all chat arms pin DeepInfra with fallback disabled after the direct DeepSeek endpoint became unavailable"
    )
    template["method"]["successor_amendment"] = str(allocation.get("reuse_reason") or "")
    template["method_policy"]["reasoningbank"] = dict(rb)
    # Register the six fixed-bank query embeddings. The conservative base bound
    # is retained and augmented rather than recomputed with a weaker formula.
    template["budget"]["call_limits"]["reasoningbank_embedding"] = 6
    template["budget"]["reasoningbank_embedding_usd"] = 6 * 8192 * (0.02 / 1_000_000)
    template["budget"]["all_in_usd"] += template["budget"]["reasoningbank_embedding_usd"] * 1.15
    runtime, inputs = build_evaluation_identity_v3(root=v622.ROOT, manifest=template)
    write_json(run / "runtime-identity.json", runtime)
    write_json(run / "runtime-identity.binding.json", {"runtime_identity_sha256": runtime["runtime_identity_sha256"],
               "runtime_identity_record_sha256": base.file_sha(run / "runtime-identity.json")})
    template["runtime_identity_inputs"] = inputs; template["runtime_identity_sha256"] = runtime["runtime_identity_sha256"]
    template["runtime_identity_file_sha256"] = base.file_sha(run / "runtime-identity.json")
    write_json(template_path, template)


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=["prepare", "freeze", "preflight", "run"])
    parser.add_argument("--run", required=True, type=Path); args = parser.parse_args(); run = args.run.resolve()
    _configure(run); base.EXTRA_RUNTIME_FACTORY = _capturing_factory
    if args.command == "prepare": prepare(run)
    elif args.command == "freeze": base.freeze(run)
    elif args.command == "preflight":
        base.load(run); _rb_manifest_record(run)
        route = verify_locked_chat_route_available()
        write_json(run / "provider-route-preflight.json", route)
        base.st(run, "preflight_passed", provider_route=route)
    else: base.run(run)


if __name__ == "__main__": main()
