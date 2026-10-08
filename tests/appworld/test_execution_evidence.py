from __future__ import annotations

import json
import os
import sys
import types
from io import StringIO
from pathlib import Path

import pytest

from copromem.benchmarks.appworld.execution_evidence import (
    DispatcherEvidenceRecorder,
    ExecutionEvidenceJournal,
    JournalPathError,
    digest,
    journal_records,
    learning_events,
    normalize_evidence_path,
    partition_v6_graph_evidence,
    prepare_evidence_journal,
)


def _registry() -> dict:
    rows = []
    for app, name, required, optional, context, outputs in (
        ("demo", "direct", ["item_id"], [], ["access_token"], ["item_id"]),
        ("demo", "loop", ["item_id"], [], [], ["item_id"]),
        ("demo", "conditional", [], ["note"], [], ["message"]),
        ("demo", "helper", [], [], [], ["message"]),
        ("demo", "failure", [], ["fail"], [], ["message"]),
    ):
        operation = f"apis.{app}.{name}"
        parameters = {field: {"type": "string", "kind": "public_required"} for field in required}
        parameters.update({field: {"type": "string", "kind": "public_optional"} for field in optional})
        parameters.update({field: {"type": "string", "kind": "runtime_context"} for field in context})
        rows.append({"operation": operation, "function_name": f"{app}__{name}", "app": app,
                     "parameters": parameters, "required_parameters": required,
                     "optional_parameters": optional, "context_parameters": context, "output_slots": outputs})
    registry = {"registry_version": "appworld-public-tool-schema-registry-v5_3", "operations": rows,
                "normalization": {"operation_aliases": {row["function_name"]: row["operation"] for row in rows},
                                  "runtime_context_fields": ["access_token"]}}
    registry["registry_sha256"] = digest(registry)
    return registry


class _Response:
    def __init__(self, status: int = 200) -> None:
        self.status_code = status

    def json(self):
        return {"message": "private response", "item": {"id": "private-id"}}


class _Requester:
    def __init__(self) -> None:
        self.state: list[str] = []

    def _request(self, _app_name: str, _api_name: str, **data):
        self.state.append(f"{_app_name}.{_api_name}")
        return _Response(400 if data.get("fail") else 200)


def _run_fixture(requester: _Requester, conditional: bool) -> list[str]:
    requester._request("demo", "direct", item_id="private-1", access_token="token")
    for item in ("private-2", "private-3"):
        requester._request("demo", "loop", item_id=item)
    if conditional:
        requester._request("demo", "conditional", note="private-note")

    def helper():
        requester._request("demo", "helper")
    helper()
    return list(requester.state)


def _records(path):
    return journal_records(path, require_e_backed=False)


def test_records_direct_loop_conditional_and_helper_execution_without_source_parsing(tmp_path):
    registry = _registry(); journal = ExecutionEvidenceJournal(tmp_path / "events.jsonl", require_e_backed=False)
    requester = _Requester()
    recorder = DispatcherEvidenceRecorder(registry, journal, "program-1", registry["registry_sha256"])
    recorder.install(requester)
    assert _run_fixture(requester, conditional=True) == ["demo.direct", "demo.loop", "demo.loop", "demo.conditional", "demo.helper"]
    # A real worker flushes after AppWorld restores its safety guard.
    assert not journal.path.exists()
    recorder.flush()
    records = _records(journal.path)
    assert [row["operation_signature"]["operation"] for row in records] == [
        "apis.demo.direct", "apis.demo.loop", "apis.demo.loop", "apis.demo.conditional", "apis.demo.helper"]
    assert [row["monotonic_index"] for row in records] == list(range(5))
    assert all(row["response_success"] and row["schema_accepted"] for row in records)
    rendered = json.dumps(records)
    assert "private-1" not in rendered and "private response" not in rendered and '"token":' not in rendered


def test_nonexecuted_branch_has_no_event_and_telemetry_is_behaviorally_transparent(tmp_path):
    baseline = _Requester(); expected_state = _run_fixture(baseline, conditional=False)
    instrumented = _Requester(); registry = _registry(); journal = ExecutionEvidenceJournal(tmp_path / "events.jsonl", require_e_backed=False)
    recorder = DispatcherEvidenceRecorder(registry, journal, "program-2", registry["registry_sha256"])
    recorder.install(instrumented)
    assert _run_fixture(instrumented, conditional=False) == expected_state == instrumented.state
    recorder.flush()
    operations = [row["operation_signature"]["operation"] for row in _records(journal.path)]
    assert "apis.demo.conditional" not in operations


def test_response_failure_unknown_schema_interrupted_write_and_tamper_fail_closed(tmp_path):
    registry = _registry(); path = tmp_path / "events.jsonl"; journal = ExecutionEvidenceJournal(path, require_e_backed=False)
    requester = _Requester(); recorder = DispatcherEvidenceRecorder(registry, journal, "program-3", registry["registry_sha256"])
    recorder.install(requester)
    requester._request("demo", "direct", item_id="private", access_token="token", unknown="x")
    requester._request("demo", "failure", fail=True)
    recorder.flush(); records = _records(path)
    _, audit = learning_events(records, registry["registry_sha256"])
    assert not audit["valid"] and {row["reason"] for row in audit["invalid"]} >= {"unknown_undeclared_field", "http_400"}
    # An interrupted trailing JSON line cannot be mistaken for a valid restart.
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"broken":')
    with pytest.raises(ValueError, match="incomplete"):
        ExecutionEvidenceJournal(path, require_e_backed=False)
    path.write_text("\n".join(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in records) + "\n", encoding="utf-8")
    tampered = json.loads(path.read_text(encoding="utf-8").splitlines()[0]); tampered["response_success"] = False
    path.write_text(json.dumps(tampered) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        ExecutionEvidenceJournal(path, require_e_backed=False)


def test_registry_mismatch_duplicate_event_and_response_attested_projection(tmp_path):
    registry = _registry(); path = tmp_path / "events.jsonl"; journal = ExecutionEvidenceJournal(path, require_e_backed=False)
    requester = _Requester(); recorder = DispatcherEvidenceRecorder(registry, journal, "program-4", registry["registry_sha256"])
    recorder.install(requester); requester._request("demo", "direct", item_id="private", access_token="token"); recorder.flush()
    records = _records(path); events, audit = learning_events(records, registry["registry_sha256"])
    assert audit["valid"] and events[0]["check"] == "native_public_response_attested"
    with pytest.raises(ValueError, match="hash differs"):
        DispatcherEvidenceRecorder(registry, journal, "other", "0" * 64)
    duplicate = dict(records[0]); duplicate["response_shape"] = {"kind": "tampered"}
    with pytest.raises(ValueError, match="duplicate conflicts"):
        journal.append(duplicate)


def test_global_frozen_runtime_context_is_not_an_undeclared_public_argument(tmp_path):
    """The dispatcher may add access_token to a locally parameterless call."""
    registry = _registry(); journal = ExecutionEvidenceJournal(tmp_path / "events.jsonl", require_e_backed=False)
    requester = _Requester(); recorder = DispatcherEvidenceRecorder(registry, journal, "program-global-context", registry["registry_sha256"])
    recorder.install(requester)
    requester._request("demo", "loop", item_id="private", access_token="runtime-secret")
    recorder.flush()
    row = _records(journal.path)[0]
    assert row["schema_accepted"]
    assert row["operation_signature"]["runtime_context_present"] == ["access_token"]
    assert "access_token" not in [item["name"] for item in row["operation_signature"]["declared_parameters"]]


def test_read_pagination_is_transport_context_but_write_and_unknown_fields_fail_closed(tmp_path):
    registry = _registry()
    for row in registry["operations"]:
        row["access_mode"] = "read" if row["operation"] == "apis.demo.loop" else "write"
    registry.pop("registry_sha256")
    registry["registry_sha256"] = digest(registry)
    journal = ExecutionEvidenceJournal(tmp_path / "pagination.jsonl", require_e_backed=False)
    requester = _Requester()
    recorder = DispatcherEvidenceRecorder(registry, journal, "pagination", registry["registry_sha256"])
    recorder.install(requester)
    requester._request("demo", "loop", item_id="private", page_index=0, page_limit=20)
    requester._request("demo", "direct", item_id="private", page_index=0, page_limit=20)
    requester._request("demo", "loop", item_id="private", undeclared="x")
    recorder.flush()
    read_row, write_row, unknown_row = _records(journal.path)
    assert read_row["schema_accepted"]
    assert read_row["operation_signature"]["runtime_context_present"] == ["page_index", "page_limit"]
    assert {item["name"] for item in read_row["operation_signature"]["declared_parameters"]} == {"item_id"}
    assert write_row["schema_error"] == "unknown_undeclared_field"
    assert unknown_row["schema_error"] == "unknown_undeclared_field"


def test_isolated_acquisition_can_audit_only_an_invalid_read_but_never_a_write(tmp_path):
    """Malformed reads cannot become graph evidence; writes remain fatal."""
    registry = _registry()
    for row in registry["operations"]:
        row["access_mode"] = "read" if row["operation"] == "apis.demo.loop" else "write"
    registry.pop("registry_sha256")
    registry["registry_sha256"] = digest(registry)
    journal = ExecutionEvidenceJournal(tmp_path / "invalid-read.jsonl", require_e_backed=False)
    requester = _Requester()
    recorder = DispatcherEvidenceRecorder(registry, journal, "invalid-read", registry["registry_sha256"])
    recorder.install(requester)
    requester._request("demo", "loop", item_id="private", undeclared="x")
    recorder.flush()
    records = _records(journal.path)
    with pytest.raises(ValueError, match="schema_mismatch"):
        partition_v6_graph_evidence(records, registry["registry_sha256"])
    eligible, audit = partition_v6_graph_evidence(
        records, registry["registry_sha256"], discard_schema_invalid_reads=True)
    assert eligible == []
    assert audit["discarded_schema_invalid_read_rows"] == 1
    assert audit["discarded_schema_invalid_reads"][0]["response_success"] is True
    # The exact same unknown field on a write must still abort before graph construction.
    write = dict(records[0])
    write["operation_signature"] = {**write["operation_signature"], "access_mode": "write"}
    write["event_sha256"] = digest({key: value for key, value in write.items() if key != "event_sha256"})
    with pytest.raises(ValueError, match="schema_mismatch"):
        partition_v6_graph_evidence([write], registry["registry_sha256"], discard_schema_invalid_reads=True)

def test_recovery_can_audit_only_unsuccessful_invalid_write_but_not_successful_write(tmp_path):
    """A rejected native call has no callable evidence; a successful one remains fatal."""
    registry = _registry()
    for row in registry["operations"]:
        row["access_mode"] = "write"
    registry.pop("registry_sha256")
    registry["registry_sha256"] = digest(registry)
    journal = ExecutionEvidenceJournal(tmp_path / "invalid-write.jsonl", require_e_backed=False)
    requester = _Requester()
    recorder = DispatcherEvidenceRecorder(registry, journal, "invalid-write", registry["registry_sha256"])
    recorder.install(requester)
    requester._request("demo", "loop", item_id="private", undeclared="x")
    recorder.flush()
    row = _records(journal.path)[0]
    assert row["schema_accepted"] is False
    failed = {**row, "response_success": False, "response_error_class": "http_422"}
    failed["event_sha256"] = digest({key: value for key, value in failed.items() if key != "event_sha256"})
    eligible, audit = partition_v6_graph_evidence(
        [failed], registry["registry_sha256"], discard_schema_invalid_unsuccessful_calls=True)
    assert eligible == []
    assert audit["discarded_schema_invalid_unsuccessful_call_rows"] == 1
    with pytest.raises(ValueError, match="schema_mismatch"):
        partition_v6_graph_evidence([row], registry["registry_sha256"], discard_schema_invalid_unsuccessful_calls=True)

def test_explicit_path_boundary_converts_windows_path_and_preflights_parent(tmp_path, monkeypatch):
    expected = (Path("/mnt/e/Project/AAMAS/evidence/events.jsonl") if os.name == "posix"
                else Path(r"E:\Project\AAMAS\evidence\events.jsonl").resolve())
    assert normalize_evidence_path(r"E:\Project\AAMAS\evidence\events.jsonl") == expected
    with pytest.raises(JournalPathError, match="path_not_absolute"):
        normalize_evidence_path("relative/events.jsonl")
    journal_path = tmp_path / "absent" / "nested" / "events.jsonl"
    old_cwd = Path.cwd(); other_cwd = tmp_path / "unrelated"; other_cwd.mkdir()
    try:
        os.chdir(other_cwd)
        journal, startup = prepare_evidence_journal(journal_path, require_e_backed=False)
    finally:
        os.chdir(old_cwd)
    assert journal.path == journal_path.resolve() and journal.path.parent.exists()
    assert startup["path_id"] == digest(str(journal_path.resolve()))
    journal.append({"parent_program_id": "program", "monotonic_index": 0, "fixture": True})
    assert len(journal_records(journal.path, require_e_backed=False)) == 1


def test_invalid_destination_fails_before_execution_evidence_can_be_created(tmp_path):
    blocked = tmp_path / "parent-file"; blocked.write_text("not a directory", encoding="utf-8")
    with pytest.raises(JournalPathError, match="mkdir_parent"):
        prepare_evidence_journal(blocked / "events.jsonl", require_e_backed=False)


def test_json_lines_worker_uses_dispatcher_evidence_without_changing_action_or_score(tmp_path, monkeypatch):
    """Exercise the real worker boundary with an isolated zero-model world."""
    from copromem.benchmarks.appworld import worker
    registry = _registry(); registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    telemetry = tmp_path / "telemetry.jsonl"

    class _Task:
        instruction = "public fixture"
        supervisor = {}
        app_descriptions = {}

    class _World:
        def __init__(self, **_):
            self.task = _Task(); self.requester = _Requester(); self.completed = False

        def execute(self, code):
            # This fixture represents a loop nested inside one submitted
            # program.  The worker can see actual dispatcher calls only.
            for item in ("one", "two"):
                self.requester._request("demo", "loop", item_id=item)
            self.completed = True
            return "same-public-output"

        def task_completed(self): return self.completed
        def evaluate(self): return types.SimpleNamespace(success=1.0, pass_count=1, fail_count=0, num_tests=1)
        def close(self): return None

    appworld = types.ModuleType("appworld"); appworld.AppWorld = _World
    monkeypatch.setitem(sys.modules, "appworld", appworld)
    monkeypatch.setattr(worker, "native_state_sha256", lambda _world: "state-sha256")
    import copromem.benchmarks.appworld.execution_evidence as evidence
    monkeypatch.setattr(evidence, "prepare_evidence_journal", lambda path: (
        evidence.ExecutionEvidenceJournal(path, require_e_backed=False),
        {"resolved_path_kind": "test_absolute", "path_id": "test", "path_identity_sha256": "test", "version": evidence.VERSION},
    ))
    monkeypatch.setenv("APPWORLD_ALLOWED_TASKS", "fixture")
    request = "\n".join(json.dumps(item) for item in [
        {"op": "start", "task_id": "fixture", "experiment_name": "fixture",
         "execution_evidence": {"registry_path": str(registry_path), "registry_sha256": registry["registry_sha256"],
                                "journal_path": str(telemetry)}},
        {"op": "action", "program_id": "fixture:action=0", "code": "nested-loop"},
        {"op": "score"}, {"op": "finish"},
    ]) + "\n"
    monkeypatch.setattr(sys, "stdin", StringIO(request)); captured = StringIO(); monkeypatch.setattr(sys, "stdout", captured)
    worker.main()
    responses = [json.loads(line) for line in captured.getvalue().splitlines()]
    assert responses[1]["output"] == "same-public-output" and responses[2]["pass_count"] == 1
    records = _records(telemetry)
    assert [row["operation_signature"]["operation"] for row in records] == ["apis.demo.loop", "apis.demo.loop"]
