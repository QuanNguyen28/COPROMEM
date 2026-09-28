"""Deterministic, zero-provider integration fixture for the v6 lifecycle.

This is deliberately a local fixture world, not an AppWorld task or official
scorer.  It drives the production dispatcher, shared-executor adapter,
execution-evidence journal, graph lifecycle, and retrieval implementation with
public-schema-compatible synthetic calls.  It is useful for engineering
regression coverage only and has no benchmark or efficacy meaning.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from ...benchmarks.appworld.execution_evidence import (
    VERSION as EVIDENCE_VERSION,
    DispatcherEvidenceRecorder,
    digest as evidence_digest,
    journal_records,
    prepare_evidence_journal,
)
from ...contrastive_graph_v6 import digest, reproduce_retrieval
from .contrastive_v6_dispatcher import ContrastiveV6Dispatcher, SharedTrajectoryExecutor
from .contrastive_v6_runner import fresh_state


FIXTURE_ID = "v6_integration_fixture_001_contrastive_graph"
POLICY_SHA256 = digest({"fixture": FIXTURE_ID, "policy": "contrastive-v6"})


class FixtureInterruption(RuntimeError):
    """Injected after a durable local checkpoint; never a provider failure."""


def _registry_body() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for operation, function_name, mode, parameters, required, outputs in (
        ("apis.demo.discover_primary", "discover_primary", "read", {"query": {"type": "string", "kind": "required"}}, ["query"], ["item_id"]),
        ("apis.demo.discover_alternative", "discover_alternative", "read", {"category": {"type": "string", "kind": "required"}}, ["category"], ["item_id"]),
        ("apis.demo.inspect", "inspect", "read", {"item_id": {"type": "string", "kind": "required"}}, ["item_id"], ["item_id"]),
        ("apis.demo.apply_effect", "apply_effect", "write", {"item_id": {"type": "string", "kind": "required"}}, ["item_id"], []),
        ("apis.demo.irrelevant_lookup", "irrelevant_lookup", "read", {"query": {"type": "string", "kind": "required"}}, ["query"], []),
    ):
        rows.append({
            "operation": operation, "app": "demo", "function_name": function_name,
            "access_mode": mode, "parameters": parameters,
            "required_parameters": required, "optional_parameters": [],
            "context_parameters": [], "output_slots": outputs,
        })
    return {
        "registry_version": "appworld-public-tool-schema-registry-v5_3",
        "operations": rows,
        "normalization": {"operation_aliases": {}},
        "dependency_edges": [
            {"from_operation": "apis.demo.discover_primary", "to_operation": "apis.demo.inspect"},
            {"from_operation": "apis.demo.discover_alternative", "to_operation": "apis.demo.inspect"},
            {"from_operation": "apis.demo.inspect", "to_operation": "apis.demo.apply_effect"},
        ],
    }


def fixture_registry() -> dict[str, Any]:
    registry = _registry_body()
    registry["registry_sha256"] = evidence_digest(registry)
    return registry


@dataclass
class ZeroProviderLedger:
    """Minimal append-only accounting boundary with exactly zero exposure."""

    records: list[dict[str, Any]] = field(default_factory=list)

    def reserve(self, role: str) -> None:
        self.records.append({"event": "reserved", "role": role, "amount_usd": 0.0})

    def settle(self, role: str) -> None:
        self.records.append({"event": "settled", "role": role, "amount_usd": 0.0})

    @property
    def unresolved(self) -> int:
        reserved = sum(item["event"] == "reserved" for item in self.records)
        settled = sum(item["event"] == "settled" for item in self.records)
        return reserved - settled


class _Response:
    status_code = 200

    def __init__(self, body: Mapping[str, Any]) -> None:
        self.body = dict(body)

    def json(self) -> dict[str, Any]:
        return dict(self.body)


class _Requester:
    def _request(self, *_: Any, **kwargs: Any) -> _Response:
        api = str(kwargs.get("_api_name"))
        if api in {"discover_primary", "discover_alternative", "inspect"}:
            return _Response({"item_id": "fixture-item"})
        return _Response({"status": "ok"})


def _append_audit_row(journal: Any, parent_program_id: str, index: int, registry_sha256: str) -> None:
    """A non-call audit row proves lifecycle telemetry cannot enter graphs."""
    journal.append({
        "version": EVIDENCE_VERSION, "parent_program_id": parent_program_id,
        "monotonic_index": index, "callable_registry_sha256": registry_sha256,
        "event_kind": "fixture_program_completed", "response_success": True,
    })


def _native_style_program(kind: str, recorder: DispatcherEvidenceRecorder) -> dict[str, Any]:
    """Direct, loop, conditional, and helper calls through the dispatcher hook."""
    requester = _Requester()
    recorder.install(requester)

    def call(api: str, **data: Any) -> _Response:
        return requester._request(_app_name="demo", _api_name=api, **data)

    def helper_apply(item_id: str) -> _Response:
        return call("apply_effect", item_id=item_id)

    if kind == "A1":
        call("irrelevant_lookup", query="fixture-discovery")
        # A loop deliberately repeats a public API call; only the directly
        # observed dispatcher events are journaled.
        for _ in range(2):
            item = call("discover_primary", query="fixture-discovery").json()["item_id"]
        if item:
            item = call("inspect", item_id=item).json()["item_id"]
        helper_apply(item)
        return {"terminal": True}
    if kind == "A2":
        item = call("discover_alternative", category="fixture-category").json()["item_id"]
        item = call("inspect", item_id=item).json()["item_id"]
        helper_apply(item)
        return {"terminal": True}
    if kind == "A3":
        call("irrelevant_lookup", query="fixture-discovery")
        item = call("discover_primary", query="fixture-discovery").json()["item_id"]
        call("inspect", item_id=item)
        return {"terminal": False}
    raise ValueError(f"unknown fixture trajectory {kind}")


def _program_without_telemetry(kind: str) -> dict[str, Any]:
    """The same local public-call control flow without the evidence wrapper."""
    requester = _Requester()
    def call(api: str, **data: Any) -> _Response:
        return requester._request(_app_name="demo", _api_name=api, **data)
    def helper_apply(item_id: str) -> _Response:
        return call("apply_effect", item_id=item_id)
    if kind != "A1":
        raise ValueError("equivalence fixture is defined for A1")
    call("irrelevant_lookup", query="fixture-discovery")
    for _ in range(2):
        item = call("discover_primary", query="fixture-discovery").json()["item_id"]
    if item:
        item = call("inspect", item_id=item).json()["item_id"]
    helper_apply(item)
    return {"terminal": True}


def run_telemetry_equivalence(root: Path) -> dict[str, Any]:
    """Verify telemetry wraps—not changes—the local public execution result."""
    root = Path(root).resolve(); registry = fixture_registry()
    path = root / "telemetry-equivalence.jsonl"
    journal, identity = prepare_evidence_journal(path)
    recorder = DispatcherEvidenceRecorder(registry, journal, "fixture-equivalence", str(registry["registry_sha256"]))
    observed = _native_style_program("A1", recorder); recorder.flush()
    _append_audit_row(journal, "fixture-equivalence", recorder.index, str(registry["registry_sha256"]))
    unobserved = _program_without_telemetry("A1")
    records = journal_records(path)
    result = {
        "fixture_id": FIXTURE_ID, "provider_calls": 0,
        "telemetry_on_return_sha256": digest(observed), "telemetry_off_return_sha256": digest(unobserved),
        "final_state_sha256": digest({"terminal": True}), "official_score": None,
        "public_call_events": len(records) - 1, "audit_events": 1,
        "nested_call_order": [row.get("operation_signature", {}).get("operation") for row in records if row.get("operation_signature")],
        "prompt_tool_interface_sha256": digest({"prompt": "", "registry_sha256": registry["registry_sha256"]}),
        "journal_identity": identity,
    }
    if result["telemetry_on_return_sha256"] != result["telemetry_off_return_sha256"]:
        raise AssertionError("telemetry changed local return value")
    if result["public_call_events"] != 5:
        raise AssertionError("direct/loop/conditional/helper evidence count mismatch")
    _write_json(root / "telemetry-on-off-equivalence.json", result)
    return result


@dataclass
class FixtureDispatch:
    root: Path
    registry: Mapping[str, Any]
    ledger: ZeroProviderLedger
    interrupt: str | None = None
    action_calls: int = 0
    scorer_calls: int = 0
    executed_actions: list[str] = field(default_factory=list)
    scored_trajectories: list[str] = field(default_factory=list)

    def _boundary_path(self, task: str, arm: str, trial: int) -> Path:
        return self.root / "fixture-boundary" / task / f"{arm}-{trial}.json"

    def __call__(self, *, task_id: str, arm: str, trial_id: int, **_: Any) -> dict[str, Any]:
        kind = {1: "A1", 2: "A2", 3: "A3"}.get(trial_id)
        if task_id != "fixture-A" or kind is None:
            raise ValueError("fixture executor is registered only for A1/A2/A3")
        boundary = self._boundary_path(task_id, arm, trial_id)
        if boundary.exists():
            saved = json.loads(boundary.read_text(encoding="utf-8"))
            if saved.get("stage") == "scored":
                return dict(saved["artifact"])
            # Action telemetry is already durable.  The restart may score it,
            # but may not re-execute the program.
            if saved.get("stage") != "telemetry":
                raise ValueError("invalid durable fixture boundary")
        else:
            evidence = self.root / "execution-evidence" / task_id / f"{arm}-{trial_id}.jsonl"
            journal, _ = prepare_evidence_journal(evidence)
            recorder = DispatcherEvidenceRecorder(self.registry, journal, f"{task_id}-{arm}-{trial_id}", str(self.registry["registry_sha256"]))
            self.ledger.reserve("fixture_native_action")
            returned = _native_style_program(kind, recorder)
            recorder.flush()
            _append_audit_row(journal, f"{task_id}-{arm}-{trial_id}", recorder.index, str(self.registry["registry_sha256"]))
            self.ledger.settle("fixture_native_action")
            self.action_calls += 1
            self.executed_actions.append(f"{task_id}/{arm}/{trial_id}")
            boundary.parent.mkdir(parents=True, exist_ok=True)
            boundary.write_text(json.dumps({"stage": "telemetry", "evidence_path": str(evidence), "return": returned}, sort_keys=True), encoding="utf-8")
            if self.interrupt == "after_telemetry":
                self.interrupt = None
                raise FixtureInterruption("injected after durable telemetry")
        saved = json.loads(boundary.read_text(encoding="utf-8"))
        self.ledger.reserve("fixture_scorer")
        score = 0.0 if kind == "A3" else 1.0
        self.ledger.settle("fixture_scorer")
        self.scorer_calls += 1
        self.scored_trajectories.append(f"{task_id}/{arm}/{trial_id}")
        artifact = {
            "arm": arm, "trial": trial_id, "after_score": score,
            "execution_evidence_path": saved["evidence_path"], "fixture_return": saved["return"],
            "fixture_scorer": "deterministic-local-not-official-appworld",
        }
        boundary.write_text(json.dumps({"stage": "scored", "artifact": artifact}, sort_keys=True), encoding="utf-8")
        if self.interrupt == "after_score":
            self.interrupt = None
            raise FixtureInterruption("injected after durable scorer outcome")
        return artifact


def _shared_executor(root: Path, registry: Mapping[str, Any], ledger: ZeroProviderLedger, dispatch: FixtureDispatch) -> SharedTrajectoryExecutor:
    return SharedTrajectoryExecutor(
        root, root / "progress.jsonl", ledger, "zero-provider-fixture", ["fixture-A", "fixture-B"],
        30, 0.7, {"version": EVIDENCE_VERSION, "registry_sha256": registry["registry_sha256"]}, dispatch=dispatch,
    )


def _trials() -> list[dict[str, Any]]:
    return [{"arm": "copromem_v6_dynamic", "trial": index, "seed": 100 + index} for index in (1, 2, 3)]


def _queries() -> list[list[str]]:
    query = ["apis.demo.inspect", "apis.demo.apply_effect"]
    return [list(query), list(query), list(query)]


def _counter_wrappers(counter: dict[str, int]) -> tuple[Callable[..., Any], Callable[..., Any], Callable[..., Any]]:
    from .contrastive_v6_runner import commit_task_batch, plan_task_batch_from_artifacts, validate_task_batch
    def planner(**kwargs: Any) -> Any:
        counter["planner"] += 1
        return plan_task_batch_from_artifacts(**kwargs)
    def validator(plan: Mapping[str, Any]) -> Any:
        counter["validator"] += 1
        return validate_task_batch(plan)
    def committer(pre_state: Mapping[str, Any], plan: Mapping[str, Any]) -> Any:
        counter["committer"] += 1
        return commit_task_batch(pre_state, plan)
    return planner, validator, committer


def _dispatcher(root: Path, registry: Mapping[str, Any], dispatch: FixtureDispatch, *, hook: Callable[[str, Mapping[str, Any]], None] | None = None, counter: dict[str, int] | None = None) -> ContrastiveV6Dispatcher:
    planner, validator, committer = _counter_wrappers(counter or {"planner": 0, "validator": 0, "committer": 0})
    return ContrastiveV6Dispatcher(root, registry, _shared_executor(root, registry, dispatch.ledger, dispatch), policy_sha256=POLICY_SHA256,
                                   planner=planner, validator=validator, committer=committer, checkpoint_hook=hook)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n"); handle.flush(); os.fsync(handle.fileno())


def run_fixture(root: Path) -> dict[str, Any]:
    """Run the positive A->B fixture and write durable, sanitized evidence."""
    root = Path(root).resolve()
    registry = fixture_registry(); ledger = ZeroProviderLedger(); dispatch = FixtureDispatch(root, registry, ledger)
    counters = {"planner": 0, "validator": 0, "committer": 0}
    lifecycle = _dispatcher(root, registry, dispatch, counter=counters)
    pre = fresh_state()
    post, marker = lifecycle.execute_batch("fixture-A", pre, _queries(), _trials())
    if marker.get("state") != "committed":
        raise AssertionError("positive fixture failed to commit")
    schema_id = str(marker["winner_schema_id"])
    schema = post["contrastive_v6_schemas"][schema_id]
    if any("fixture-" in json.dumps(value, ensure_ascii=False) for value in (schema, post)):
        raise AssertionError("concrete fixture value leaked into learned state")
    # A second construction is an exact restart: no new executor/scorer or
    # planner/validator/commit boundary may run.
    before_counts = {**counters, "actions": dispatch.action_calls, "scorers": dispatch.scorer_calls}
    lifecycle = _dispatcher(root, registry, dispatch, counter=counters)
    replay_post, replay_marker = lifecycle.execute_batch("fixture-A", pre, _queries(), _trials())
    if replay_post != post or replay_marker != marker or before_counts != {**counters, "actions": dispatch.action_calls, "scorers": dispatch.scorer_calls}:
        raise AssertionError("restart replayed a completed production boundary")
    lifecycle.authorize_b("fixture-A", "fixture-B")
    b_queries = [["apis.demo.inspect", "apis.demo.apply_effect"], ["apis.demo.inspect", "apis.demo.apply_effect"]]
    b = lifecycle.prepare("fixture-B", post, b_queries)
    if len({item["pre_state_sha256"] for item in b}) != 1 or any(not item["guidance"] for item in b):
        raise AssertionError("B did not receive same-state learned guidance")
    for item in b:
        if item["provenance"]["selected_schema_id"] != schema_id:
            raise AssertionError("B did not select A schema")
        if reproduce_retrieval(post, item["query"], item["provenance"]) != item["guidance"]:
            raise AssertionError("B retrieval was not reproducible")
    negative_guidance = lifecycle.prepare("fixture-B-negative", fresh_state(), [["apis.demo.irrelevant_lookup"], ["apis.demo.irrelevant_lookup"]])
    if any(row["guidance"] or row["provenance"]["fallback_category"] != "empty" for row in negative_guidance):
        raise AssertionError("incompatible retrieval supplied generic guidance")
    fixed_retrievals = lifecycle.prepare("fixture-fixed", post, b_queries)
    if digest(post) != marker["after_state_sha256"] or any(row["provenance"]["pre_state_sha256"] != digest(post) for row in fixed_retrievals):
        raise AssertionError("fixed retrieval mutated semantic state")
    final = {
        "fixture_id": FIXTURE_ID, "classification": "ENGINEERING-VALIDATED",
        "provider_calls": 0, "official_appworld_scorer": False,
        "fixture_scorer": "deterministic-local-not-official-appworld",
        "registry_sha256": registry["registry_sha256"], "pre_state_sha256": digest(pre),
        "post_state_sha256": digest(post), "schema_id": schema_id, "schema_sha256": digest(schema),
        "plan_sha256": marker["plan_sha256"], "validation_sha256": digest(marker["validation"]),
        "a_scores": [1.0, 1.0, 0.0], "b_retrieval_hashes": [row["record_sha256"] for row in b],
        "b_guidance_sha256": b[0]["provenance"]["guidance_sha256"],
        "negative_fallback": negative_guidance[0]["provenance"]["fallback_category"],
        "ledger": {"records": ledger.records, "unresolved": ledger.unresolved},
        "call_counters": {**counters, "external_actions": dispatch.action_calls, "scorers": dispatch.scorer_calls},
    }
    _write_json(root / "final-fixture-report.json", final)
    _write_json(root / "state-machine-transition-record.json", {
        task: sorted(path.name for path in (root / "state-machine" / task).glob("*.json"))
        for task in ("fixture-A", "fixture-B", "fixture-B-negative", "fixture-fixed")
        if (root / "state-machine" / task).exists()
    })
    _write_json(root / "promoted-schema-audit.json", {"schema_id": schema_id, "schema": schema, "marker": marker})
    _write_json(root / "a-to-b-retrieval-audit.json", {"records": b, "negative": negative_guidance})
    _write_json(root / "evidence-checksums.json", {"final_sha256": digest(final), "post_state_sha256": digest(post),
                                                      "a_evidence_paths": [str(root / "execution-evidence" / "fixture-A" / f"copromem_v6_dynamic-{n}.jsonl") for n in (1, 2, 3)]})
    return final


def run_restart_drills(root: Path) -> dict[str, Any]:
    """Exercise restart checkpoints without repeating local external calls."""
    root = Path(root).resolve(); registry = fixture_registry(); pre = fresh_state(); rows: list[dict[str, Any]] = []
    for stage in ("after_telemetry", "after_score", "batch_ready", "plan_persisted", "validation_persisted", "commit_persisted"):
        case = root / stage; ledger = ZeroProviderLedger(); dispatch = FixtureDispatch(case, registry, ledger,
                                                                                        interrupt=stage if stage.startswith("after_") else None)
        counters = {"planner": 0, "validator": 0, "committer": 0}
        fired = {"value": False}
        def hook(transition: str, _: Mapping[str, Any]) -> None:
            if transition == stage and not fired["value"]:
                fired["value"] = True; raise FixtureInterruption(f"injected after {stage}")
        initial = _dispatcher(case, registry, dispatch, hook=None if stage.startswith("after_") else hook, counter=counters)
        try:
            initial.execute_batch("fixture-A", pre, _queries(), _trials())
        except FixtureInterruption:
            pass
        action_before, scorer_before = dispatch.action_calls, dispatch.scorer_calls
        resumed = _dispatcher(case, registry, dispatch, counter=counters)
        post, marker = resumed.execute_batch("fixture-A", pre, _queries(), _trials())
        if (marker["state"] != "committed" or dispatch.action_calls != 3 or dispatch.scorer_calls != 3
                or len(set(dispatch.executed_actions)) != len(dispatch.executed_actions)
                or len(set(dispatch.scored_trajectories)) != len(dispatch.scored_trajectories)):
            raise AssertionError(f"restart repeated external boundary at {stage}")
        rows.append({"stage": stage, "post_state_sha256": digest(post), "actions_before_resume": action_before,
                     "scorers_before_resume": scorer_before, "counters": dict(counters)})
    # B retrieval persistence interruption: restart may only create the second
    # retrieval, while preserving the first record byte-for-byte.
    case = root / "after_one_b_retrieval"; ledger = ZeroProviderLedger(); dispatch = FixtureDispatch(case, registry, ledger)
    d = _dispatcher(case, registry, dispatch); post, _ = d.execute_batch("fixture-A", pre, _queries(), _trials()); d.authorize_b("fixture-A", "fixture-B")
    fired = {"value": False}
    def b_hook(transition: str, _: Mapping[str, Any]) -> None:
        if transition == "retrieval_persisted" and not fired["value"]:
            fired["value"] = True; raise FixtureInterruption("after first B retrieval")
    try:
        _dispatcher(case, registry, dispatch, hook=b_hook).prepare("fixture-B", post, [["apis.demo.inspect", "apis.demo.apply_effect"], ["apis.demo.inspect", "apis.demo.apply_effect"]])
    except FixtureInterruption:
        pass
    first = (case / "retrievals" / "fixture-B" / "trial-1.json").read_bytes()
    rows_b = _dispatcher(case, registry, dispatch).prepare("fixture-B", post, [["apis.demo.inspect", "apis.demo.apply_effect"], ["apis.demo.inspect", "apis.demo.apply_effect"]])
    if first != (case / "retrievals" / "fixture-B" / "trial-1.json").read_bytes() or len(rows_b) != 2:
        raise AssertionError("B retrieval restart was not idempotent")
    rows.append({"stage": "after_one_b_retrieval", "first_retrieval_preserved": True})
    _write_json(root / "restart-replay-matrix.json", {"fixture_id": FIXTURE_ID, "rows": rows})
    return {"fixture_id": FIXTURE_ID, "rows": rows}
