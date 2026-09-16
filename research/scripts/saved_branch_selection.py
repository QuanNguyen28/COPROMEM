"""Offline policies over existing immutable branches; no new native/model calls."""

from __future__ import annotations

import json
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest
from copromem.stateful_adapter import verify_prefix_pair
from copromem.stateful_effect import api_log_count, error_indices

VERSION = "known-branch-manual-selection-ceiling-v1"
POLICIES = ("no_op", "always_edit", "manual_all_clear", "manual_risk_reduction")


def public_findings(manual: dict, warning_names: list[str]) -> dict:
    if set(manual) != {"version", "scope", "pagination", "consumer_risks", "decision"}:
        raise ValueError("unexpected manual finding metadata")
    page = manual["pagination"]
    risks = {"name:" + n for n in warning_names}
    if page["status"] == "risk":
        risks.update("pagination:" + r for r in page["reasons"])
    risks.update("consumer:" + r for r in manual["consumer_risks"])
    return {
        "risks": sorted(risks),
        "unknown": page["status"] not in {"risk", "pattern_observed"},
    }


def selections(public: dict) -> dict:
    if set(public) != {"original", "edited"}:
        raise ValueError("activation input contains nonpublic fields")
    for side in public.values():
        if (
            set(side) != {"risks", "unknown"}
            or type(side["unknown"]) is not bool
            or not isinstance(side["risks"], list)
            or any(not isinstance(r, str) for r in side["risks"])
        ):
            raise ValueError("invalid public risk summary")
        if side["risks"] != sorted(set(side["risks"])):
            raise ValueError("risk reasons must be canonical")
    before, after = public["original"], public["edited"]
    known = not (before["unknown"] or after["unknown"])
    return {
        "no_op": False,
        "always_edit": True,
        "manual_all_clear": known and bool(before["risks"]) and not after["risks"],
        "manual_risk_reduction": known and set(after["risks"]) < set(before["risks"]),
    }


def evaluate(rows: list[dict]) -> dict:
    if not rows:
        raise ValueError("nonempty branch-pair sample required")
    result = {}
    for policy in (*POLICIES, "quality_oracle"):
        successes = beneficial = harmful = chosen = headroom = 0
        counts = []
        missing_cost = 0
        for row in rows:
            before, after = row["original_success"], row["edited_success"]
            if type(before) is not bool or type(after) is not bool:
                raise ValueError("native branch outcomes must be booleans")
            decision = (
                after and not before
                if policy == "quality_oracle"
                else row["selections"][policy]
            )
            if type(decision) is not bool:
                raise ValueError("policy selection must be boolean")
            success = after if decision else before
            successes += success
            beneficial += success and not before
            harmful += before and not success
            chosen += decision
            headroom += (before or after) and not success
            cost = (
                row["edited_api_entries"] if decision else row["original_api_entries"]
            )
            missing_cost += cost is None
            if cost is not None:
                counts.append(cost)
        result[policy] = {
            "pairs": len(rows),
            "edits_selected": chosen,
            "successes": successes,
            "beneficial_vs_no_op": beneficial,
            "harmful_vs_no_op": harmful,
            "oracle_quality_headroom": headroom,
            "selected_native_api_entries": sum(counts) if not missing_cost else None,
            "missing_cost_pairs": missing_cost,
        }
    return result


def require(condition, message):
    if not condition:
        raise IntegrityError(message)


def main():
    root = Path(__file__).resolve().parents[2]
    source = RunStore(root / "artifacts/research/cycle22_static_name_check")
    static_key = "44089b0c774a60e7f942675dbccb0b77e3d2e81f6fdeb68af51205a8383dfe8a"
    static = source.read("reports", static_key)
    manual_store = RunStore(root / "artifacts/research/post22_manual_coverage_control")
    manual_key = "f0f6d56e74663d66cf6c297f889c63efdf6b632a049c5f403f2fd5e48af7ba71"
    manual = manual_store.read("reports", manual_key)
    require(
        digest(static) == static_key and digest(manual) == manual_key,
        "source report changed",
    )
    protocol = source.read("protocol", "preregistration")
    require(digest(protocol) == static["protocol_digest"], "source protocol changed")
    cases = [source.read("cases", key) for key in protocol["case_ids"]]
    require(
        len(cases) == 14 and len(manual["rows"]) == 14,
        "fourteen-record source incomplete",
    )
    for key, case in zip(protocol["case_ids"], cases, strict=True):
        require(digest(case) == key, "source case changed")
    original_indices = (10, 11, 12)
    edit_indices = (*range(10), 13)
    controls = {cases[i]["checkpoint_digest"]: i for i in original_indices}
    require(len(controls) == 3, "factual checkpoint identities are not unique")
    b = {r["case_index"]: r for r in static["rows"] if r["context"]}
    findings = []
    for i, row in enumerate(manual["rows"]):
        require(
            row["record"] == i
            and row["source_case_id"] == protocol["case_ids"][i] == b[i]["case_id"],
            "manual/static row binding changed",
        )
        findings.append(public_findings(row["manual"], b[i]["parsed"]["warning_names"]))
    # The selected view digests and model-independent policy decisions are fixed
    # before this runner attaches native branch outcomes and API costs.
    choices = [
        (
            controls[cases[i]["checkpoint_digest"]],
            i,
            selections(
                {
                    "original": findings[controls[cases[i]["checkpoint_digest"]]],
                    "edited": findings[i],
                }
            ),
        )
        for i in edit_indices
    ]
    rows = []
    for oi, ei, selected in choices:
        original, edited = cases[oi], cases[ei]
        stores = [RunStore(Path(c["source_store"])) for c in (original, edited)]
        cells = [c["source_cell"] + "-live" for c in (original, edited)]
        requests = [
            s.read("worker_requests", c) for s, c in zip(stores, cells, strict=True)
        ]
        index = original["action_index"]
        require(
            index == edited["action_index"]
            and original["origin_episode"] == edited["origin_episode"],
            "pair origin/action mismatch",
        )
        require(
            requests[0]["actions"][index] == original["public_input"]["program"],
            "original action mismatch",
        )
        expected = {
            **requests[0],
            "actions": [
                *requests[0]["actions"][:index],
                edited["public_input"]["program"],
                *requests[0]["actions"][index + 1 :],
            ],
        }
        require(requests[1] == expected, "pair changes more than the target action")
        frames = [
            s.read("stream_frames", c + "-000")
            for s, c in zip(stores, cells, strict=True)
        ]
        identity = verify_prefix_pair(
            frames[0], frames[1], expected_error_indices=error_indices(frames[0])
        )
        labels, costs = [], []
        evidence = []
        for c, store, key, request in zip(
            (original, edited), stores, cells, requests, strict=True
        ):
            worker = store.read("worker_results", key)
            native = store.read("native_evaluation", key)
            require(
                worker["request_id"] == digest(request)
                and [r["program"] for r in worker["results"]] == request["actions"]
                and native["native_success"] == c["final_native_success_audit_only"]
                and native["task_id"] == request["task_id"],
                "saved native branch identity changed",
            )
            labels.append(native["native_success"])
            costs.append(api_log_count(store, key, request["task_id"]))
            evidence.append(
                {
                    "request_digest": digest(request),
                    "worker_digest": digest(worker),
                    "native_digest": digest(native),
                }
            )
        rows.append(
            {
                "original_record": oi,
                "edited_record": ei,
                "origin_episode": original["origin_episode"],
                "task_id": requests[0]["task_id"],
                "checkpoint_digest": original["checkpoint_digest"],
                "prefix_identity_check_digest": digest(identity),
                "branch_evidence": evidence,
                "public_findings": {"original": findings[oi], "edited": findings[ei]},
                "selections": selected,
                "original_success": labels[0],
                "edited_success": labels[1],
                "original_api_entries": costs[0],
                "edited_api_entries": costs[1],
            }
        )
    # Inventory only: do NOT claim to have run the manual policy on these other
    # native effects or borrow a presence observation from a different checkpoint.
    inventory = []
    for folder, key in (
        (
            "cycle17_boundary_effects",
            "34d849a67422629d7c6c6b35761794ed44c21765928d61fa1ff9856de415264c",
        ),
        (
            "cycle18_bound_effects",
            "41f762eab2b0f87b9088e6c9234986d00c4b94245b6d87aa8a09b3bf7a6b5465",
        ),
    ):
        store = RunStore(root / "artifacts/research" / folder)
        report = store.read("reports", key)
        require(digest(report) == key, "inventory effect report changed")
        for row in report["rows"]:
            if row["factual"]:
                continue
            require(
                store.read("effect_cells", row["cell_id"]) == row,
                "effect inventory row changed",
            )
            inventory.append(
                {
                    "source_report": key,
                    "cell_id": row["cell_id"],
                    "origin_episode": row["origin_episode"],
                    "action_index": row["action_index"],
                    "eligible": row["eligible"],
                    "original_success": row["original_native_success"],
                    "edited_success": row["native_evaluation"]["native_success"],
                    "included_in_this_policy_sample": folder == "cycle18_bound_effects"
                    and row["cell_id"] == "c18b-edit-02",
                    "exact_public_context_available": row["checkpoint_digest"]
                    in controls,
                }
            )
    require(
        len(inventory) == 31
        and sum(x["included_in_this_policy_sample"] for x in inventory) == 1,
        "effect inventory denominator changed",
    )
    paths = (
        Path(__file__).resolve(),
        root / "tests/test_saved_branch_selection.py",
        root / "research/060_SAVED_BRANCH_SELECTION_DIAGNOSTIC.md",
        root / "src/copromem/checkpoints.py",
        root / "src/copromem/stateful_adapter.py",
        root / "src/copromem/stateful_effect.py",
    )
    texts = {
        p.relative_to(root).as_posix(): p.read_text(encoding="utf-8") for p in paths
    }
    report = {
        "version": VERSION,
        "static_report": static_key,
        "manual_report": manual_key,
        "source_snapshot": digest(texts),
        "rows": rows,
        "aggregate": evaluate(rows),
        "other_effect_inventory": inventory,
        "additional_inventory_records_not_policy_evaluated": 30,
        "known_scenarios_in_policy_sample": sorted({r["task_id"] for r in rows}),
        "distinct_policy_sample_checkpoints": len(
            {r["checkpoint_digest"] for r in rows}
        ),
        "model_calls": 0,
        "native_executions": 0,
        "api_usd": 0,
        "learned_component_value": None,
        "decision": "REVISE",
        "interpretation": "Post-hoc selection among previously verified fixed native branches; quality ceiling only for these eleven correlated known-build opportunities. No learned policy, new native intervention, admission or held-out efficacy.",
    }
    store = RunStore(root / "artifacts/research/post22_saved_branch_selection")
    store.bind_provenance({"report_digest": digest(report)})
    store.write("source_snapshots", digest(texts), texts)
    store.write("reports", digest(report), report)
    print(
        json.dumps(
            {
                "report_digest": digest(report),
                **{
                    k: v
                    for k, v in report.items()
                    if k not in {"rows", "other_effect_inventory"}
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
