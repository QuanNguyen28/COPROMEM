"""Frozen contrast/success-only proposal diagnostic, isolated from native tasks."""

from __future__ import annotations

import argparse
import json
import math
import runpy
from datetime import datetime, timezone
from pathlib import Path

from copromem.checkpoints import GenerationService, IntegrityError, RecordedCallError, RunStore, digest
from copromem.providers import BudgetedOpenRouterClient, BudgetLedger, model_endpoints
from copromem.real_gsm8k_experiment import load_env

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
INPUT = runpy.run_path(str(HERE / "monitor_proposal_inputs.py"))
SANDBOX = runpy.run_path(str(HERE / "monitor_sandbox.py"))
INPUT_REPORT = "2890a5e8a9eebbd78e0f737bb2214f3a66585847946bc7b0a6c6963fb2f0f48f"
SANDBOX_REPORT = "d2061cd58e5acc90e5354af9d3ad3ca4cf234218ee1a1d9a0c26ee2b935948ed"
NAMESPACE = "cycle23-richer-monitor-proposal-v1"
PROVIDER_CONFIGURATION = {"provider": INPUT["PROVIDER"], "allow_fallbacks": False, "max_prompt_price_per_million": 0.5, "max_completion_price_per_million": 2.0}
INTERFACE = """Exact runtime interface (identical in both evidence conditions):
Only plain top-level functions; judge has exactly program and present_names as
positional parameters, no default values or annotations. Helpers may be other
top-level plain functions. No decorators, nested functions, async/generators,
lambdas, type parameters, global/nonlocal, with, try/except or raise statements.
No identifier, parameter, function or attribute name may start with underscore.
Do not assign or delete object attributes. ast exposes public AST node classes
and only parse, walk, iter_child_nodes, iter_fields, dump, unparse, literal_eval,
get_source_segment. Other ast module globals are unavailable. No getattr or type;
use isinstance and the public AST fields. Builtins are exactly those listed above.
present_names is an immutable tuple of observed names. Code is an inspection
string, not an environment where it can be executed. There are no native APIs.
Output exactly one JSON object with source and scope_note, no Markdown fences.
Source limit is 16000 UTF-8 bytes and 3000 AST nodes; scope_note at most 4000 chars.
The judge has 1 CPU second and 128 MB container memory; return True/False/None.
"""


def check_snapshot(store, key):
    texts = store.read("source_snapshots", key)
    if texts is None or digest(texts) != key or any((ROOT / name).read_text(encoding="utf-8") != text for name, text in texts.items()):
        raise IntegrityError("frozen source snapshot differs from current implementation")
    return texts


def final_request(base):
    return {**base, "system": base["system"] + "\n" + INTERFACE}


def transport_request(payload):
    return {"namespace": NAMESPACE, "model": INPUT["MODEL"], "provider_configuration": PROVIDER_CONFIGURATION, "temperature": 0, **payload}


def validate_endpoint(metadata, max_input_bytes):
    endpoints = [e for e in metadata.get("endpoints", []) if e.get("tag") == INPUT["PROVIDER"] and e.get("model_id") == INPUT["MODEL"]]
    if len(endpoints) != 1:
        raise IntegrityError("registered model/provider endpoint is not uniquely listed")
    endpoint = endpoints[0]
    for name, ceiling in (("prompt", 0.5), ("completion", 2.0)):
        price = float(endpoint["pricing"][name]) * 1_000_000
        if not math.isfinite(price) or price < 0 or price > ceiling:
            raise IntegrityError("registered endpoint exceeds token-price ceiling")
    if not {"seed", "temperature", "max_tokens"}.issubset(endpoint.get("supported_parameters", [])):
        raise IntegrityError("registered request parameters not supported")
    if endpoint["context_length"] < max_input_bytes + INPUT["MAX_TOKENS"] + 1024 or (endpoint.get("max_completion_tokens") or INPUT["MAX_TOKENS"]) < INPUT["MAX_TOKENS"]:
        raise IntegrityError("registered endpoint context/output capacity insufficient")
    return endpoint


def prepare(store):
    inputs = RunStore(ROOT / "artifacts/research/cycle23_monitor_inputs")
    input_report = inputs.read("reports", INPUT_REPORT)
    if digest(input_report) != INPUT_REPORT:
        raise IntegrityError("input-preflight report changed")
    check_snapshot(inputs, input_report["source_snapshot"])
    # Both calls reconstruct saved evidence only; neither executes fresh checks.
    cases, audit = INPUT["collect"]()
    if digest(audit) != input_report["source_audit"]:
        raise IntegrityError("registered source audit changed")
    preflight = RunStore(ROOT / "artifacts/research/cycle23_monitor_sandbox_preflight")
    sandbox_report = preflight.read("reports", SANDBOX_REPORT)
    if digest(sandbox_report) != SANDBOX_REPORT or not sandbox_report["all_passed"]:
        raise IntegrityError("isolated-runtime preflight is not complete and passing")
    check_snapshot(preflight, sandbox_report["source_snapshot"])
    runpy.run_path(str(HERE / "preflight_monitor_sandbox.py"))["main"]()
    slots = []
    for row in input_report["prepared_requests"]:
        base = INPUT["request"](cases, row["fold"], row["mode"], row["seed"])
        if digest(base) != row["request_digest"] or inputs.read("prepared_requests", digest(base)) != base:
            raise IntegrityError("base request/evidence does not regenerate")
        payload = final_request(base)
        slot = {"key": f"f{row['fold']}-{row['mode']}-s{row['seed']}", "fold": row["fold"], "mode": row["mode"], "seed": row["seed"], "base_request_digest": digest(base), "request_digest": digest(payload), "transport_request_digest": digest(transport_request(payload))}
        store.write("prepared_requests", digest(payload), payload)
        slots.append(slot)
    views, labels = [], []
    for i, case in enumerate(cases):
        public = INPUT["runtime_input"](case["public_input"])
        expected = input_report["runtime_inputs"][i]
        if expected != {"index": i, "source_case_id": digest(case), "input_id": digest(public)} or inputs.read("runtime_inputs", digest(public)) != public:
            raise IntegrityError("diagnostic runtime input differs from frozen source")
        store.write("runtime_inputs", digest(public), public)
        views.append(digest(public))
        labels.append(case["final_native_success_audit_only"])
    paths = [HERE / name for name in ("run_monitor_proposals.py", "monitor_proposal_inputs.py", "monitor_source_policy.py", "monitor_sandbox_driver.py", "monitor_sandbox.py", "preflight_monitor_sandbox.py")]
    paths.extend(ROOT / name for name in ("src/copromem/checkpoints.py", "src/copromem/providers.py", "src/copromem/real_gsm8k_experiment.py", "tests/test_monitor_proposal_runner.py", "tests/test_monitor_sandbox.py", "research/053_CYCLE23_MONITOR_PROPOSAL_PROTOCOL.md", "research/055_CYCLE23_SANDBOX_AND_INTERFACE_FREEZE.md"))
    texts = {p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8") for p in paths}
    protocol = {"cycle": NAMESPACE, "input_report": INPUT_REPORT, "sandbox_report": SANDBOX_REPORT, "source_snapshot": digest(texts), "slots": slots, "runtime_input_ids": views, "audit_only_saved_outcome_labels": labels, "model": INPUT["MODEL"], "provider_configuration": PROVIDER_CONFIGURATION, "max_usd": 5.0, "max_http_attempts": 36, "native_executions": 0, "admitted_contracts": 0}
    store.bind_provenance({"protocol_digest": digest(protocol)})
    store.write("protocol", "preregistration", protocol)
    store.write("source_snapshots", digest(texts), texts)
    return protocol


def metrics(protocol, rows):
    slots = protocol["slots"]
    if len(slots) != 12 or len(rows) != 12 or {r["key"] for r in rows} != {s["key"] for s in slots}:
        raise IntegrityError("complete twelve-slot denominator required")
    counts = {mode: [0, 0] for mode in ("contrast", "success_only")}
    qualified = []
    for slot, row in zip(slots, rows, strict=True):
        if row["key"] != slot["key"] or row["mode"] != slot["mode"] or row["fold"] != slot["fold"]:
            raise IntegrityError("candidate slot identity/order mismatch")
        correct = []
        if row["status"] == "valid_candidate":
            if len(row["predictions"]) != 14:
                raise IntegrityError("complete fourteen-input candidate predictions required")
            for i, prediction in enumerate(row["predictions"]):
                verdict = prediction["result"]["verdict"]
                if prediction["result"]["status"] == "ok" and type(verdict) is bool and verdict is protocol["audit_only_saved_outcome_labels"][i]:
                    correct.append(i)
        passed = {10, 6, 12, 13}.issubset(correct)
        if passed:
            counts[slot["mode"]][slot["fold"]] += 1
            qualified.append(slot["key"])
    complete_provider = all(row["status"] in {"valid_candidate", "invalid_candidate"} for row in rows)
    primary = complete_provider and all(n >= 2 for n in counts["contrast"])
    return {"planned_requests": 12, "complete_provider_sample": complete_provider, "qualifying_counts_by_fold": counts, "qualifying_candidate_keys": qualified, "paired_count_difference_by_fold": [a - b for a, b in zip(counts["contrast"], counts["success_only"], strict=True)], "primary_passed": primary, "decision": "KEEP" if primary else "REVISE", "admitted_contracts": 0, "native_executions": 0, "interpretation": "Known-build proposal consistency only; not learned semantic correctness, contrast superiority, native recovery or held-out transfer."}


def collect_proposals(store, protocol, service):
    rows, provider_stopped = [], False
    for slot in protocol["slots"]:
        key = slot["key"]
        payload = store.read("prepared_requests", slot["request_digest"])
        if digest(payload) != slot["request_digest"]:
            raise IntegrityError("frozen generation request changed")
        row = store.read("proposal_outcomes", key)
        if row is not None:
            rows.append(row)
            provider_stopped = provider_stopped or row["status"] == "provider_failed"
            continue
        row = {"key": key, "fold": slot["fold"], "mode": slot["mode"], "seed": slot["seed"], "transport_request_digest": slot["transport_request_digest"], "predictions": []}
        if provider_stopped:
            row["status"] = "not_attempted_after_provider_failure"
        else:
            attempted = store.read("proposal_attempts", key)
            if attempted is not None and store.read("calls", slot["transport_request_digest"]) is None:
                raise IntegrityError("unresolved paid proposal attempt; no silent regeneration")
            store.write("proposal_attempts", key, {"request_digest": slot["transport_request_digest"]})
            try:
                generation = service.call(**payload)
            except RecordedCallError:
                row["status"] = "provider_failed"
                provider_stopped = True
            else:
                if generation.request_id != slot["transport_request_digest"]:
                    raise IntegrityError("provider call differs from frozen request")
                row["call_id"] = generation.request_id
                try:
                    parsed = SANDBOX["parse_candidate"](generation.text)
                except (ValueError, TypeError, SyntaxError, RecursionError) as exc:
                    row.update(status="invalid_candidate", error_type=type(exc).__name__, policy_reason=str(exc) if type(exc).__name__ == "PolicyError" else None)
                else:
                    row.update(status="valid_candidate", candidate_id=digest(parsed))
                    store.write("candidates", digest(parsed), parsed)
                    for index, input_id in enumerate(protocol["runtime_input_ids"]):
                        public = store.read("runtime_inputs", input_id)
                        if digest(public) != input_id:
                            raise IntegrityError("frozen runtime input corrupted")
                        result = SANDBOX["run_case"](store, f"{key}-i{index:02d}", parsed["candidate"]["source"], public)
                        row["predictions"].append(result)
        store.write("proposal_outcomes", key, row)
        rows.append(row)
        print(json.dumps({"slot": key, "status": row["status"], "completed_runtime_inputs": len(row["predictions"])}), flush=True)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, default=ROOT / "artifacts/research/cycle23_monitor_proposals")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--env", type=Path, default=ROOT / ".env")
    args = parser.parse_args()
    store = RunStore(args.store)
    protocol = prepare(store)
    if not args.execute:
        print(json.dumps({"protocol_digest": digest(protocol), "source_snapshot": protocol["source_snapshot"], "prepared_requests": 12, "model_calls": 0, "stage": "complete_freeze_ready_for_provider_check"}, indent=2))
        return
    metadata = model_endpoints(protocol["model"])
    payloads = [store.read("prepared_requests", s["request_digest"]) for s in protocol["slots"]]
    max_bytes = max(len(p["system"].encode("utf-8")) + len(p["user"].encode("utf-8")) for p in payloads)
    endpoint = validate_endpoint(metadata, max_bytes)
    check = {"utc": datetime.now(timezone.utc).isoformat(), "metadata": metadata, "selected_endpoint": endpoint}
    store.write("provider_checks", digest(check), check)
    key = load_env(args.env).get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is unavailable")
    ledger = BudgetLedger(store, 5.0, 36)
    client = BudgetedOpenRouterClient(key, INPUT["MODEL"], INPUT["PROVIDER"], ledger, prompt_price_per_million=0.5, completion_price_per_million=2.0)
    service = GenerationService(client, store, NAMESPACE)
    rows = collect_proposals(store, protocol, service)
    report = {"protocol_digest": digest(protocol), "rows": rows, **metrics(protocol, rows), "completed_model_calls": len(list((store.root / "calls").glob("*.json"))), "http_attempts": len(ledger.reservations), "settled_usd": sum(ledger.settlements.values()), "charged_or_reserved_usd": ledger.charged_or_reserved, "sandbox_processes": len(list((store.root / "sandbox_processes").glob("*.json")))}
    store.write("reports", digest(report), report)
    print(json.dumps({"report_digest": digest(report), **{k: v for k, v in report.items() if k != "rows"}}, indent=2), flush=True)


if __name__ == "__main__":
    main()
