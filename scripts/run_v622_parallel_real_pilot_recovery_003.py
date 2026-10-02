#!/usr/bin/env python3
"""Recovery of real-pilot 015 after its first CoProMem Dynamic batch fault.

The predecessor is immutable.  This wrapper reuses the generic atomic import
engine but admits its complete 18-trajectory first-task prefix.  CoProMem and
ReasoningBank retrieval records remain predecessor-owned sidecars: they are
verified against their original artifact/runtime before being used to complete
the deterministic CoProMem task-boundary transaction.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from scripts import run_v61_exploratory_evaluation as runner
from scripts import run_v622_parallel_baseline_pilot as parallel
from scripts import run_v622_parallel_real_pilot_recovery_002 as recovery
from copromem.experiments.reme_copromem.recovery_import import RecoveryImportError, file_sha256
from copromem.experiments.reme_copromem.retrieval_binding_v622 import validate as validate_copro_binding


PROTOCOL = "v6.2.2-real-pilot-100-recovery-003-v1"
SOURCE_PROTOCOL = "v6.2.2-real-pilot-100-recovery-002-v1"
SOURCE_RUN = parallel.REVIEW / "artifacts/research/official_reme_copromem_pilot/v6_2_2_real_pilot_100_015_recovery"
PREFIX_COUNT = 18
_SOURCE_REASONINGBANK_CONTEXTS: dict[Path, Mapping[str, Any]] = {}
LEGACY_UNSEALED_REASONINGBANK_PROTOCOL = "v6.2.2-real-pilot-100-recovery-002-v1"


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RecoveryImportError("carried retrieval evidence is unreadable") from exc
    if not isinstance(value, dict):
        raise RecoveryImportError("carried retrieval evidence has the wrong shape")
    return value


def _source_of(target_artifact: Path) -> tuple[Path, Path, dict[str, Any], dict[str, Any]]:
    target = _load(target_artifact)
    carried = target.get("carried_completed_from")
    if not isinstance(carried, Mapping):
        raise RecoveryImportError("imported artifact lacks source custody")
    source_run = Path(str(carried.get("source_run_path") or ""))
    source_artifact = Path(str(carried.get("source_artifact_path") or ""))
    if (not source_run.is_absolute() or not source_artifact.is_absolute()
            or not source_artifact.is_file()
            or file_sha256(source_artifact) != carried.get("source_artifact_sha256")):
        raise RecoveryImportError("imported artifact source custody is invalid")
    source = _load(source_artifact)
    for field in ("trajectory_id", "task_id", "arm", "trial_id", "seed", "history_sha256",
                  "after_score", "actions", "termination"):
        if target.get(field) != source.get(field):
            raise RecoveryImportError("imported artifact differs from its immutable source")
    return source_run, source_artifact, source, target


def _validate_carried_copromem(run: Path, _manifest: Mapping[str, Any], artifact_path: Path,
                               retrieval_path: Path, *, state: Mapping[str, Any],
                               registry: Mapping[str, Any], reproduce: Any) -> None:
    source_run, source_artifact, source, target = _source_of(artifact_path)
    name = f"{source['arm']}-{source['trial_id']}.json"
    source_retrieval = source_run / "retrievals" / str(source["task_id"]) / name
    source_binding = source_retrieval.with_suffix(".binding.json")
    if not source_retrieval.is_file() or not source_binding.is_file() or not retrieval_path.is_file():
        raise RecoveryImportError("imported CoProMem retrieval custody is incomplete")
    if retrieval_path.read_bytes() != source_retrieval.read_bytes():
        raise RecoveryImportError("imported CoProMem retrieval bytes differ from source")
    validate_copro_binding(artifact_path=source_artifact, retrieval_path=source_retrieval,
                           binding_path=source_binding,
                           runtime_identity_record_path=source_run / "runtime-identity.json",
                           state=state, registry=registry, reproduce=reproduce)
    for field in ("copromem_callback_guidance_sha256", "copromem_callback_guidance_nonempty",
                  "injected_memory_sha256", "initial_prompt_messages_sha256",
                  "model_visible_prompt_sha256"):
        if target.get(field) != source.get(field):
            raise RecoveryImportError("imported CoProMem prompt binding differs from source")


def _validate_carried_reasoningbank(context: Mapping[str, Any] | None, run: Path,
                                    _manifest: Mapping[str, Any], arm: str, task: str,
                                    trial: int, seed: int, artifact: Path,
                                    _result: Mapping[str, Any]) -> None:
    if arm != parallel.REASONINGBANK_ARM:
        return parallel._existing_validator(context, run, _manifest, arm, task, trial, seed, artifact, _result)
    source_run, source_artifact, source, target = _source_of(artifact)
    if context is None:
        raise RecoveryImportError("ReasoningBank runtime is absent while verifying carried artifact")
    # Retrieval identities include the source manifest and runtime identity.
    # Reconstruct a read-only fixed-bank context for that immutable source;
    # validating it through the successor context would falsely compare two
    # different, correctly sealed prompts.
    source_context = _SOURCE_REASONINGBANK_CONTEXTS.get(source_run)
    source_manifest = _load(source_run / "manifest.json")
    if source_context is None:
        source_context = parallel._runtime_factory(
            source_run, source_manifest,
            runner.AppendOnlyLedger(source_run / "ledger.jsonl", float(source_manifest["budget"]["hard_cap_usd"])),
            "recovery-verification-no-dispatch",
            _load(runner.REG),
        )
        _SOURCE_REASONINGBANK_CONTEXTS[source_run] = source_context
    source_retrieval = source_run / "retrievals" / task / f"{arm}-{trial}.json"
    verified = parallel.verify(
        path=source_retrieval,
        store=parallel.ContentAddressedStore(source_run / "reasoningbank-retrieval-objects"),
        expected_bank_sha256=str(source_context["initial_sha256"]),
        require_prompt_binding=False,
    )
    if verified["identity"] != parallel._identity(source_run, source_manifest, task, trial, seed):
        raise RecoveryImportError("carried ReasoningBank retrieval identity differs from source schedule")
    binding = verified.get("prompt_binding")
    modern_seal_matches = (isinstance(binding, Mapping)
                           and source.get("initial_prompt_messages_sha256")
                           == binding.get("initial_prompt_messages_sha256"))
    if not modern_seal_matches:
        # The three predecessor records predate persisted prompt bindings.
        # They are admissible only as explicitly legacy, source-bound custody:
        # never reconstructed as a successor prompt seal and never accepted for
        # any future protocol version.
        if source_manifest.get("protocol") != LEGACY_UNSEALED_REASONINGBANK_PROTOCOL:
            raise RecoveryImportError("unsealed ReasoningBank retrieval is outside the legacy custody protocol")
        if not isinstance(source.get("initial_prompt_messages_sha256"), str):
            raise RecoveryImportError("legacy ReasoningBank artifact lacks its recorded prompt digest")
    target_retrieval = run / "retrievals" / task / f"{arm}-{trial}.json"
    if (not source_retrieval.is_file() or not target_retrieval.is_file()
            or target_retrieval.read_bytes() != source_retrieval.read_bytes()):
        raise RecoveryImportError("imported ReasoningBank retrieval bytes differ from source")
    if target.get("initial_prompt_messages_sha256") != source.get("initial_prompt_messages_sha256"):
        raise RecoveryImportError("imported ReasoningBank prompt binding differs from source")


def _terminal_check(run: Path, manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    context = parallel._ACTIVE_CONTEXT
    if context is None:
        raise RuntimeError("ReasoningBank terminal context is absent")
    count = 0
    for task in manifest["evaluation"]["task_ids"]:
        for trial, seed in enumerate(manifest["evaluation"]["seeds"], 1):
            artifact = run / "artifacts" / task / parallel.REASONINGBANK_ARM / f"trial-{trial}.json"
            row = _load(artifact)
            if isinstance(row.get("carried_completed_from"), Mapping):
                _validate_carried_reasoningbank(context, run, manifest, parallel.REASONINGBANK_ARM,
                                                str(task), trial, seed, artifact, row)
            else:
                parallel._verify_one(context, run, manifest, str(task), trial, seed, artifact)
            count += 1
    if context["runtime"].lifecycle.bank.state()["semantic_state_sha256"] != context["initial_sha256"]:
        raise RuntimeError("ReasoningBank fixed bank mutated")
    return {"valid": True, "retrieval_count": count,
            "fixed_bank_sha256": context["initial_sha256"], "carried_retrievals_verified": PREFIX_COUNT // 6}


_original_configure = recovery._configure


def _configure(run: Path, *, historical_exposure: Any = None) -> None:
    _original_configure(run, historical_exposure=historical_exposure)
    runner.EXTRA_CARRIED_COPRO_VALIDATOR = _validate_carried_copromem
    runner.EXTRA_EXISTING_VALIDATOR = _validate_carried_reasoningbank
    runner.EXTRA_TERMINAL_CHECK = _terminal_check


recovery.PROTOCOL = PROTOCOL
recovery.SOURCE_PROTOCOL = SOURCE_PROTOCOL
recovery.SOURCE_RUN = SOURCE_RUN
recovery.PREFIX_COUNT = PREFIX_COUNT
recovery._configure = _configure


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "freeze", "recover", "preflight", "run"])
    parser.add_argument("--run", required=True, type=Path)
    args = parser.parse_args()
    run = args.run.resolve()
    {"prepare": recovery.prepare, "freeze": recovery.freeze, "recover": recovery.recover,
     "preflight": recovery.preflight, "run": recovery.run}[args.command](run)


if __name__ == "__main__":
    main()
