#!/usr/bin/env python3
"""Read-only, value-redacted terminal audit for ReasoningBank engineering 006.

The audit consumes only durable local evidence.  It never constructs an
AppWorld task, starts a service, reads a credential, or crosses a provider
boundary.  Its report deliberately contains identities, hashes, public task
roles, and aggregate statistics only--not instructions, histories, journals,
memory text, scorer payloads, or provider responses.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import sys
from collections.abc import Mapping
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from copromem.experiments.reme_copromem.live_summary import reconcile_ledger
from copromem.integrations.reasoning_bank.appworld import (  # noqa: E402
    MEMORY_PROMPT,
    ReasoningBank,
    load_state,
    sha256,
)
from copromem.integrations.reasoning_bank.checkpoints import (  # noqa: E402
    ReasoningBankDynamicCheckpoints,
)


RUN_NAME = "reasoningbank_appworld_engineering_006_clean_restart"
DEFAULT_RUN = pathlib.Path(
    "E:/Project/AAMAS/reasoningbank-appworld-artifacts/"
    "reasoningbank_appworld_engineering_006_clean_restart"
)
DEFAULT_OUTPUT = ROOT / "research/reasoningbank_appworld/v621-reasoningbank-engineering-006-final-audit.json"
DEFAULT_CHECKSUMS = ROOT / "research/reasoningbank_appworld/v621-reasoningbank-engineering-006-final-audit.checksums.json"
DEFAULT_MARKDOWN = ROOT / "research/reasoningbank_appworld/REASONINGBANK_ENGINEERING_006_FINAL_AUDIT.md"
EXPECTED_MANIFEST = "8f68bcead88dcfcad3af319de2580e0e10c8a25f578dff474a4c2aa2772393e6"
EXPECTED_RECONCILED = "3b9c44462e1afc5f593ffb26e685d9899a4b89718ef988b1a2b25f9432daf347"
EXPECTED_SOURCE = "a315f6ed371c15c25fc975fb3a970e563398a929"
EXPECTED_PUBLICATION = "ed0e271a5ec9060e770ff1c1e0aecd6244643b73"


class AuditError(RuntimeError):
    """A frozen-run invariant is absent, ambiguous, or inconsistent."""


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditError(f"unreadable JSON evidence: {path.name}") from exc
    if not isinstance(value, dict):
        raise AuditError(f"expected JSON object: {path.name}")
    return value


def host_path(value: str) -> pathlib.Path:
    """Project an immutable E-backed path onto this reader's host spelling."""
    if value.startswith("/mnt/e/") and os.name == "nt":
        return pathlib.Path("E:/" + value[len("/mnt/e/"):])
    if os.name != "nt" and re.match(r"^[Ee]:[\\/]", value):
        return pathlib.Path("/mnt/e/" + value[3:].replace("\\", "/"))
    return pathlib.Path(value)


def _artifact_key(row: Mapping[str, Any]) -> tuple[str, str, int, int]:
    try:
        return (str(row["arm"]), str(row["task_id"]), int(row["trial_id"]), int(row["seed"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise AuditError("artifact has malformed trajectory identity") from exc


def _scorer_valid(row: Mapping[str, Any]) -> tuple[str, str]:
    """Validate only hash-bound scorer metadata; never export scorer rows."""
    zero = row.get("zero_action_evidence")
    if isinstance(zero, Mapping):
        copy = dict(zero)
        binding = copy.pop("binding_sha256", None)
        path = host_path(str(zero.get("scorer_evidence_path") or ""))
        if binding != digest(copy) or not path.is_file() or file_sha(path) != zero.get("scorer_evidence_sha256"):
            raise AuditError("zero-action scorer evidence binding is invalid")
        if zero.get("official_score") != row.get("after_score"):
            raise AuditError("zero-action scorer score differs from artifact")
        return "zero_action", str(zero["scorer_evidence_sha256"])
    scorer = row.get("official_scorer_evidence")
    if not isinstance(scorer, Mapping):
        raise AuditError("ordinary artifact has no scorer evidence")
    path = host_path(str(scorer.get("path") or ""))
    if not path.is_file() or file_sha(path) != scorer.get("sha256"):
        raise AuditError("ordinary scorer evidence binding is invalid")
    if scorer.get("trajectory_id") != row.get("trajectory_id") or scorer.get("task_id") != row.get("task_id"):
        raise AuditError("ordinary scorer identity differs from artifact")
    if scorer.get("official_score") != row.get("after_score"):
        raise AuditError("ordinary scorer score differs from artifact")
    return "ordinary", str(scorer["sha256"])


def _validate_artifact(path: pathlib.Path, run: pathlib.Path, manifest: Mapping[str, Any], runtime_sha: str) -> dict[str, Any]:
    row = read(path)
    key = _artifact_key(row)
    if row.get("termination") not in {"completed", "truncation_termination"}:
        raise AuditError("artifact has an unregistered termination")
    history = row.get("history")
    if not isinstance(history, list) or not history or digest(history) != row.get("history_sha256"):
        raise AuditError("artifact history is absent or hash-inconsistent")
    actions = sum(isinstance(message, Mapping) and message.get("role") == "assistant" for message in history)
    if actions != int(row.get("actions", -1)):
        raise AuditError("artifact action count differs from canonical history")
    journal = host_path(str(row.get("execution_evidence_path") or ""))
    if not journal.is_absolute() or not journal.is_file():
        raise AuditError("artifact journal is absent or not absolute")
    try:
        relative = journal.resolve().relative_to(run.resolve()).as_posix()
    except ValueError as exc:
        raise AuditError("artifact journal escapes the frozen run") from exc
    payload = journal.read_bytes()
    if row.get("execution_evidence_sha256") != hashlib.sha256(payload).hexdigest():
        raise AuditError("artifact journal hash differs from durable file")
    if row.get("execution_evidence_rows") != len(payload.splitlines()):
        raise AuditError("artifact journal row count differs from durable file")
    if row.get("execution_evidence_run_relative") != relative:
        raise AuditError("artifact portable journal locator differs from durable file")
    if row.get("execution_evidence_registry_sha256") != manifest.get("registry_sha256"):
        raise AuditError("artifact registry identity differs from manifest")
    if row.get("runtime_identity_sha256") != runtime_sha:
        raise AuditError("artifact runtime identity differs from frozen runtime record")
    if payload:
        try:
            events = [json.loads(line) for line in payload.splitlines()]
        except json.JSONDecodeError as exc:
            raise AuditError("execution-evidence journal has malformed JSONL") from exc
        # Native evidence restarts its monotonic index for each response-
        # attested parent program.  A global strictly increasing sequence would
        # therefore reject valid nested-call journals.  The immutable contract
        # instead requires a non-negative index on every independently
        # attested row; its durable file order remains the cross-program order.
        indices = [event.get("monotonic_index") for event in events if isinstance(event, Mapping)]
        if len(indices) != len(events) or any(not isinstance(index, int) or index < 0 for index in indices):
            raise AuditError("execution-evidence journal has malformed monotonic indices")
    elif "zero_action_evidence" not in row:
        raise AuditError("empty journal lacks canonical zero-action evidence")
    scorer_variant, scorer_sha = _scorer_valid(row)
    return {
        "key": key,
        "row": row,
        "artifact_sha256": file_sha(path),
        "journal_sha256": row["execution_evidence_sha256"],
        "journal_rows": row["execution_evidence_rows"],
        "scorer_variant": scorer_variant,
        "scorer_sha256": scorer_sha,
    }


def _rendered_guidance(bank: ReasoningBank, selected: list[str]) -> str:
    by_id = {item.experience_id: item for item in bank.experiences}
    if len(selected) > 1 or any(item not in by_id for item in selected):
        raise AuditError("retrieval selects a missing or non-top-1 experience")
    blocks = [block for item_id in selected for block in by_id[item_id].memory_items if block.strip()]
    guidance = "\n\n".join(blocks)
    return (MEMORY_PROMPT + "\n\n" + guidance).strip() if guidance else ""


def retrieval_selection_reproducibility(provenance: Mapping[str, Any]) -> tuple[bool, str]:
    """State the exact provenance needed to independently reproduce top-1.

    A query-vector hash authenticates a vector that was once present, but it
    cannot recompute cosine ranking or deterministic append-order tie-breaking.
    The value itself must be durably available for a zero-provider replay.
    """
    vector = provenance.get("query_embedding")
    if not isinstance(vector, list) or not vector:
        return False, "query_embedding_values_absent; hash_only_cannot_recompute_cosine_top1"
    if provenance.get("query_embedding_sha256") != sha256([float(item) for item in vector]):
        return False, "query_embedding_hash_mismatch"
    return True, "reproducible"


def _checkpoint_audit(run: pathlib.Path, manifest: Mapping[str, Any]) -> tuple[dict[str, Any], dict[int, ReasoningBank]]:
    initial = ReasoningBank.restore(dict(manifest["initial_bank"]))
    expected = [
        f"evaluation:reasoningbank_dynamic:{task}:trial={trial}:seed={seed}"
        for task in manifest["evaluation"]["task_ids"]
        for trial, seed in enumerate(manifest["evaluation"]["seeds"], 1)
    ]
    manager = ReasoningBankDynamicCheckpoints(
        root=run / "reasoningbank-dynamic-checkpoints", expected_trajectory_ids=expected,
        ledger_path=run / "ledger.jsonl",
    )
    reconciliation = manager.reconcile(initial)
    if reconciliation.next_trajectory_id is not None or len(reconciliation.completed) != len(expected):
        raise AuditError("Dynamic checkpoint chain is incomplete")
    pre_states: dict[int, ReasoningBank] = {1: initial}
    for index in range(2, len(expected) + 1):
        pre_states[index] = load_state(run / "reasoningbank-dynamic-checkpoints" / "snapshots" / f"{index - 1:04d}.json")
    markers = []
    for completion in reconciliation.completed:
        marker_path = run / "reasoningbank-dynamic-checkpoints" / "completion-markers" / f"{completion.update_index:04d}.json"
        marker = read(marker_path)
        markers.append({
            "update_index": completion.update_index,
            "trajectory_id": completion.trajectory_id,
            "pre_state_sha256": marker["pre_update_semantic_state_sha256"],
            "post_state_sha256": marker["post_update_semantic_state_sha256"],
            "marker_sha256": file_sha(marker_path),
            "snapshot_sha256": marker["source_snapshot_sha256"],
            "verifier_dump_sha256": marker["verifier_dump_sha256"],
            "settled_provider_id_count": len(marker["newly_settled_provider_ids"]),
            "restart_reproduction": True,
        })
    return {
        "complete_prefix_length": len(markers),
        "next_permitted_trajectory": None,
        "markers": markers,
        "final_semantic_state_sha256": reconciliation.restored_bank.state()["semantic_state_sha256"],
        "fixed_bank_immutability": "not_applicable; no ReasoningBank Fixed arm was registered",
    }, pre_states


def _retrieval_rows(run: pathlib.Path, manifest: Mapping[str, Any], artifacts: Mapping[tuple[str, str, int, int], Mapping[str, Any]], pre_states: Mapping[int, ReasoningBank]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    tasks = list(manifest["evaluation"]["task_ids"])
    seeds = list(manifest["evaluation"]["seeds"])
    rows: list[dict[str, Any]] = []
    for index, (task, trial, seed) in enumerate(((task, trial, seed) for task in tasks for trial, seed in enumerate(seeds, 1)), 1):
        record = read(run / "retrievals" / task / f"reasoningbank_dynamic-trial-{trial}.json")
        provenance = record.get("retrieval_provenance")
        if not isinstance(provenance, Mapping):
            raise AuditError("retrieval record has no provenance")
        forbidden = {"official_score", "after_score", "before_score", "history", "scorer", "future_action", "post_outcome"}
        if forbidden & (set(record) | set(provenance)):
            raise AuditError("retrieval record contains prohibited scorer or outcome provenance")
        state = pre_states[index]
        selected = [str(item) for item in provenance.get("selected_experience_ids", [])]
        if record.get("bank_pre_state_sha256") != state.state()["semantic_state_sha256"] or provenance.get("pre_state_sha256") != state.state()["semantic_state_sha256"]:
            raise AuditError("retrieval state does not equal its durable Dynamic prefix")
        rendered = _rendered_guidance(state, selected)
        if sha256(rendered) != record.get("guidance_sha256"):
            raise AuditError("retrieval guidance cannot be reconstructed from selected durable state")
        artifact = artifacts[("reasoningbank_dynamic", task, trial, seed)]
        if artifact.get("injected_memory_sha256") != record.get("guidance_sha256"):
            raise AuditError("artifact memory binding differs from retrieval guidance")
        visible = bool(artifact.get("injected_memory_visible_in_initial_prompt"))
        expected_binding = sha256({
            "prompt": artifact.get("model_visible_prompt_sha256"),
            "memory": artifact.get("injected_memory_sha256"),
            "visible": visible,
        })
        if artifact.get("model_visible_memory_binding_sha256") != expected_binding:
            raise AuditError("artifact prompt-memory binding is inconsistent")
        if bool(record.get("guidance_nonempty")) != bool(selected) or bool(artifact.get("injected_memory_nonempty")) != bool(selected):
            raise AuditError("retrieval/selected/prompt non-empty states differ")
        if not state.experiences and not selected:
            selection_reproducible, reproduction_reason = True, "empty_bank_has_no_top1_candidate"
        else:
            selection_reproducible, reproduction_reason = retrieval_selection_reproducibility(provenance)
        source_tasks = {item.experience_id: item.task_id for item in state.experiences}
        role = "A" if task == tasks[0] else "B" if task == tasks[1] else "N_negative_control"
        if not selected:
            relevance = "no_candidate"
        elif role == "B" and tasks[0] in [source_tasks[item] for item in selected]:
            relevance = "predeclared_A_B_public_descriptor_match"
        elif all(source_tasks[item] == task for item in selected):
            relevance = "same_task_prior_experience"
        else:
            relevance = "cross_family_not_semantically_relevant"
        rows.append({
            "task_id": task,
            "task_role": role,
            "trial": trial,
            "seed": seed,
            "dynamic_update_index": index,
            "score": artifact["after_score"],
            "action_count": artifact["actions"],
            "pre_state_sha256": state.state()["semantic_state_sha256"],
            "retrieval_empty": bool(provenance.get("retrieval_empty")),
            "selected_experience_ids": selected,
            "selected_source_task_ids": [source_tasks[item] for item in selected],
            "semantic_relevance": relevance,
            "similarity_score_durably_persisted": False,
            "guidance_sha256": record["guidance_sha256"],
            "guidance_render_reconstructed": True,
            "top1_selection_offline_reproducible": selection_reproducible,
            "selection_reproduction_reason": reproduction_reason,
            "prompt_visible": visible,
            "empty_prompt_identical_to_no_memory": (
                artifact.get("model_visible_prompt_sha256") == artifacts[("no_memory", task, trial, seed)].get("model_visible_prompt_sha256")
                if not selected else None
            ),
            "prompt_memory_binding_sha256": artifact["model_visible_memory_binding_sha256"],
            "temporal_admissibility": all(item in source_tasks for item in selected),
            "self_judge_outcome": None,
        })
    # Each post-update snapshot ends in the experience made by that update.
    for row in rows:
        snapshot = load_state(run / "reasoningbank-dynamic-checkpoints" / "snapshots" / f"{row['dynamic_update_index']:04d}.json")
        row["self_judge_outcome"] = snapshot.experiences[-1].status
    transfer = [row for row in rows if row["task_role"] == "B" and tasks[0] in row["selected_source_task_ids"]]
    negative = [row for row in rows if row["task_role"] == "N_negative_control"]
    return rows, {
        "a_to_b_selected_prior_a_experience": bool(transfer),
        "a_to_b_first_b_trial_selected_a": bool(transfer and transfer[0]["trial"] == 1),
        "negative_control_nonempty_retrieval_count": sum(not item["retrieval_empty"] for item in negative),
        "negative_control_cross_family_retrieval": any(tasks[0] in item["selected_source_task_ids"] for item in negative),
        "negative_control_interpretation": "expected upstream top-1/no-abstention behavior; it is a negative-transfer risk, not evidence of relevance",
        "selected_schema_relevance_classes": sorted({item["semantic_relevance"] for item in rows}),
    }


def _score_rows(artifacts: Mapping[tuple[str, str, int, int], Mapping[str, Any]], manifest: Mapping[str, Any]) -> dict[str, Any]:
    tasks, seeds = manifest["evaluation"]["task_ids"], manifest["evaluation"]["seeds"]
    rows = []
    paired = {"reasoningbank_dynamic": {"wins": 0, "ties": 0, "losses": 0, "differences": []}}
    for task in tasks:
        for trial, seed in enumerate(seeds, 1):
            base = float(artifacts[("no_memory", task, trial, seed)]["after_score"])
            dynamic = float(artifacts[("reasoningbank_dynamic", task, trial, seed)]["after_score"])
            delta = dynamic - base
            outcome = "win" if delta > 0 else "loss" if delta < 0 else "tie"
            paired["reasoningbank_dynamic"][{"win": "wins", "tie": "ties", "loss": "losses"}[outcome]] += 1
            paired["reasoningbank_dynamic"]["differences"].append(delta)
            rows.extend((
                {"task_id": task, "trial": trial, "seed": seed, "arm": "no_memory", "score": base,
                 "action_count": artifacts[("no_memory", task, trial, seed)]["actions"]},
                {"task_id": task, "trial": trial, "seed": seed, "arm": "reasoningbank_dynamic", "score": dynamic,
                 "action_count": artifacts[("reasoningbank_dynamic", task, trial, seed)]["actions"], "paired_difference_vs_no_memory": delta, "paired_outcome": outcome},
            ))
    stats = paired["reasoningbank_dynamic"]
    stats["mean_paired_difference"] = sum(stats.pop("differences")) / 6
    return {"per_task_trial_scores": rows, "paired_against_no_memory": paired}


def audit(run: pathlib.Path) -> dict[str, Any]:
    run = run.resolve()
    manifest = read(run / "manifest.json")
    manifest_sha = file_sha(run / "manifest.json")
    if manifest_sha != EXPECTED_MANIFEST or (run / "manifest.sha256").read_text(encoding="utf-8").strip() != manifest_sha:
        raise AuditError("frozen manifest identity is inconsistent")
    if manifest.get("git_commit") != EXPECTED_SOURCE or manifest.get("allocation_publication_commit") != EXPECTED_PUBLICATION:
        raise AuditError("frozen source/publication identity differs from the approved run")
    runtime_file_sha = file_sha(run / "runtime-identity.json")
    runtime_identity = read(run / "runtime-identity.json")
    runtime_sha = runtime_identity.get("runtime_identity_sha256")
    # The manifest binds the canonical runtime-content identity; artifacts bind
    # the exact durable runtime-identity file.  Those are deliberately
    # different preimages and must not be conflated.
    if runtime_sha != manifest.get("runtime_identity_sha256"):
        raise AuditError("runtime-content identity differs from frozen manifest")
    artifacts: dict[tuple[str, str, int, int], dict[str, Any]] = {}
    details = []
    for path in sorted((run / "artifacts").glob("*/*/trial-*.json")):
        item = _validate_artifact(path, run, manifest, runtime_file_sha)
        if item["key"] in artifacts:
            raise AuditError("duplicate trajectory artifact identity")
        artifacts[item["key"]] = item["row"]
        details.append({key: item[key] for key in ("key", "artifact_sha256", "journal_sha256", "journal_rows", "scorer_variant", "scorer_sha256")})
    expected = {(arm, task, trial, seed) for arm in manifest["arms"] for task in manifest["evaluation"]["task_ids"] for trial, seed in enumerate(manifest["evaluation"]["seeds"], 1)}
    if set(artifacts) != expected or len(artifacts) != 12:
        raise AuditError("artifact inventory is not the exact frozen 12-trajectory schedule")
    ledger = reconcile_ledger(run / "ledger.jsonl", historical_expected_usd=manifest["historical_infrastructure_exposure_usd"],
                              historical_id=manifest["historical_carry_forward_id"], registered_arms=manifest["arms"])
    if ledger.unresolved_reservation_ids:
        raise AuditError("ledger has unresolved reservations")
    for arm, task, trial, seed in artifacts:
        role = f"executor:{arm}:{task}:trial={trial}:seed={seed}"
        if not any(call.role == role and call.settled_usd is not None for call in ledger.calls):
            raise AuditError("artifact has no settled executor role")
    checkpoints, pre_states = _checkpoint_audit(run, manifest)
    retrievals, transfer = _retrieval_rows(run, manifest, artifacts, pre_states)
    scores = _score_rows(artifacts, manifest)
    status, marker, final = read(run / "runner-status.json"), read(run / "run-reconciled.json"), read(run / "final-report.json")
    if status.get("state") != "completed" or status.get("run_reconciled_sha256") != EXPECTED_RECONCILED:
        raise AuditError("runner terminal status is not valid")
    if marker.get("record_sha256") != EXPECTED_RECONCILED or marker.get("manifest_sha256") != manifest_sha:
        raise AuditError("run-reconciled marker is not bound to manifest")
    if final.get("manifest_sha256") != manifest_sha or final.get("run_reconciled_sha256") != EXPECTED_RECONCILED:
        raise AuditError("final report is not bound to terminal marker")
    complete_top1 = all(item["top1_selection_offline_reproducible"] for item in retrievals)
    classification = "ENGINEERING-VALIDATED" if complete_top1 and transfer["a_to_b_first_b_trial_selected_a"] else "INVALID-METHOD-INTEGRATION"
    dynamic = [item for item in retrievals]
    self_judge_agreement = sum(
        (item["self_judge_outcome"] == "success") == (float(item["score"]) == 1.0) for item in dynamic
    )
    report = {
        "version": "reasoningbank-appworld-engineering-006-final-audit-v1",
        "zero_provider": True,
        "run": {"name": RUN_NAME, "manifest_sha256": manifest_sha, "executable_commit": EXPECTED_SOURCE,
                "publication_commit": EXPECTED_PUBLICATION, "runtime_content_identity_sha256": runtime_sha,
                "runtime_identity_file_sha256": runtime_file_sha,
                "registry_sha256": manifest["registry_sha256"], "terminal_reconciliation_sha256": EXPECTED_RECONCILED,
                "completed_trajectories": 12},
        "integrity": {
            "unique_registered_trajectories": len(artifacts), "artifact_rows": details,
            "ledger": {"reservations": len(ledger.calls), "settlements": sum(call.settled_usd is not None for call in ledger.calls),
                       "unresolved": len(ledger.unresolved_reservation_ids), "historical_exposure_usd": float(ledger.historical_settled_exposure),
                       "evaluation_exposure_usd": float(ledger.settled_evaluation_cost), "total_exposure_usd": float(ledger.total_ledger_exposure),
                       "ledger_sha256": ledger.ledger_sha256},
            "terminal_bindings_valid": True,
            "fixed_bank_immutability": checkpoints["fixed_bank_immutability"],
        },
        "dynamic_checkpoint_chain": checkpoints,
        "retrievals": retrievals,
        "a_to_b_transfer": transfer,
        "self_judge_audit": {"trajectory_count": len(dynamic), "full_score_agreement_count": self_judge_agreement,
                               "agreement_interpretation": "self-judge labels are recorded separately from official scores and are not a causal efficacy measure"},
        "score_analysis": scores,
        "admission": {
            "guidance_rendering_reconstructed_from_selected_state": all(item["guidance_render_reconstructed"] for item in retrievals),
            "temporal_admissibility": all(item["temporal_admissibility"] for item in retrievals),
            "prompt_visibility": all(
                item["prompt_visible"] if not item["retrieval_empty"] else item["empty_prompt_identical_to_no_memory"]
                for item in retrievals
            ),
            "top1_selection_offline_reproducible": complete_top1,
            "top1_selection_failure_reason": "persisted provenance contains only query_embedding_sha256, not normalized query_embedding values or similarity scores",
            "leakage_audit": "no scorer field, official score, future action, or post-outcome field is an input to the retrieval record; this audit nevertheless cannot independently recompute top-1 selection from a hash-only query embedding",
        },
        "interpretation": {
            "classification": classification,
            "permitted_claim": "None: the terminal evidence is durable, but the frozen retrieval provenance cannot independently reproduce cosine top-1 selection byte-for-byte.",
            "prohibited_claims": ["efficacy", "superiority", "generalization", "causal score attribution", "reproducible retrieval selection"],
            "negative_control_note": "The negative control retrieved an A-family experience under frozen upstream top-1/no-abstention behavior. This is recorded as potential negative transfer, not as relevant retrieval.",
            "next_required_method_amendment": "Persist normalized query-embedding values and exact top-1 similarity/tie-break evidence in a versioned retrieval-provenance contract before a new paid comparison.",
        },
        "sanitization": {"excluded": ["instructions", "histories", "journal rows", "memory text", "scorer payloads", "provider responses", "credentials"]},
    }
    report["audit_sha256"] = digest(report)
    return report


def write_report(report: Mapping[str, Any], output: pathlib.Path, checksums: pathlib.Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    files = {output.name: file_sha(output)}
    if DEFAULT_MARKDOWN.is_file():
        files[DEFAULT_MARKDOWN.name] = file_sha(DEFAULT_MARKDOWN)
    checksums.write_text(json.dumps({"version": "v1", "files": files}, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=pathlib.Path, default=DEFAULT_RUN)
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--checksums", type=pathlib.Path, default=DEFAULT_CHECKSUMS)
    args = parser.parse_args()
    report = audit(args.run)
    write_report(report, args.output, args.checksums)
    print(json.dumps({"classification": report["interpretation"]["classification"], "audit_sha256": report["audit_sha256"], "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
