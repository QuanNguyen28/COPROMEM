"""Value-redacted evidence for *executed* public AppWorld API dispatches.

This module intentionally instruments AppWorld's shared ``Requester._request``
boundary.  It never parses submitted Python to infer calls: loops, branches,
comprehensions, and helpers are represented only when the native dispatcher is
actually entered.  The persisted form contains public callable metadata and
hashes, never invocation values, responses, task instructions, or scorer data.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping


VERSION = "public-execution-evidence-v1"

# AppWorld''s native read dispatcher accepts these pagination controls on list
# endpoints even where its frozen callable schema omitted them. They are
# transport metadata, never learned procedure arguments. Writes deliberately
# do not receive this compatibility allowance.
_READ_TRANSPORT_CONTEXT_FIELDS = frozenset({"page_index", "page_limit"})

class JournalPathError(RuntimeError):
    """Sanitized, deterministic error for the external durability boundary."""

    def __init__(self, stage: str, path: Path, error: OSError | None = None) -> None:
        self.stage, self.path = stage, path
        self.errno = getattr(error, "errno", None)
        self.error_type = None if error is None else type(error).__name__
        super().__init__(
            f"execution evidence journal {stage} failed error_type={self.error_type} "
            f"errno={self.errno} path_id={digest(str(path))}"
        )


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _shape(value: Any, depth: int = 0) -> Any:
    """A bounded response shape with field names/types but no response values."""
    if depth >= 2:
        return {"kind": type(value).__name__}
    if isinstance(value, Mapping):
        return {"kind": "object", "fields": {str(key): _shape(item, depth + 1)
                for key, item in sorted(value.items(), key=lambda item: str(item[0]))}}
    if isinstance(value, (list, tuple)):
        return {"kind": "array", "item": _shape(value[0], depth + 1) if value else {"kind": "empty"}}
    return {"kind": type(value).__name__}


def _response_shape(response: Any) -> dict[str, Any]:
    try:
        return _shape(response.json())
    except Exception:
        return {"kind": "unavailable"}


def _response_output_hashes(response: Any, output_slots: list[str]) -> dict[str, str]:
    """Retain equality witnesses for declared outputs, never their values."""
    try:
        body = response.json()
    except Exception:
        return {}
    if not isinstance(body, Mapping):
        return {}
    return {name: digest(body[name]) for name in sorted(set(output_slots) & set(body))}


def _registry_digest(registry: Mapping[str, Any]) -> str:
    body = {key: value for key, value in registry.items() if key != "registry_sha256"}
    return digest(body)


def _registry_index(registry: Mapping[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    if registry.get("registry_version") != "appworld-public-tool-schema-registry-v5_3":
        raise ValueError("unsupported public callable registry version")
    if registry.get("registry_sha256") != _registry_digest(registry):
        raise ValueError("public callable registry hash mismatch")
    rows = registry.get("operations")
    aliases = registry.get("normalization", {}).get("operation_aliases")
    if not isinstance(rows, list) or not isinstance(aliases, Mapping):
        raise ValueError("public callable registry is malformed")
    index = {str(row["operation"]): dict(row) for row in rows if isinstance(row, Mapping)}
    if len(index) != len(rows):
        raise ValueError("public callable registry contains duplicate operations")
    return index, {str(key): str(value) for key, value in aliases.items()}


def runtime_context_fields(registry: Mapping[str, Any]) -> frozenset[str]:
    """Return the frozen, task-independent dispatcher context field set.

    AppWorld injects authentication context into some calls even when the
    individual callable's public declaration has no explicit parameter.  The
    v5.3 registry freezes this classification in its normalization metadata.
    These fields are never learned API arguments.
    """
    normalization = registry.get("normalization", {})
    fields = normalization.get("runtime_context_fields", ()) if isinstance(normalization, Mapping) else ()
    if not isinstance(fields, (list, tuple)) or any(not isinstance(value, str) or not value for value in fields):
        raise ValueError("public callable registry has malformed runtime context fields")
    return frozenset(fields)


def _operation_record(registry: Mapping[str, Any], app_name: str, api_name: str, data: Mapping[str, Any]) -> dict[str, Any]:
    index, aliases = _registry_index(registry)
    submitted = f"apis.{app_name}.{api_name}"
    operation = aliases.get(submitted, submitted)
    meta = index.get(operation)
    values = {str(key): data[key] for key in sorted(data)}
    value_hashes = {key: digest(value) for key, value in values.items()}
    if meta is None:
        return {"schema_accepted": False, "schema_error": "unknown_public_callable", "operation": operation,
                "submitted_operation": submitted, "invocation_value_hashes": value_hashes,
                "invocation_values_sha256": digest(values)}
    parameters = meta.get("parameters", {})
    names = set(values)
    known = set(parameters)
    context = set(meta.get("context_parameters", ())) | set(runtime_context_fields(registry))
    if meta.get("access_mode") == "read":
        context |= _READ_TRANSPORT_CONTEXT_FIELDS
    unknown = sorted(names - known - context)
    required = set(meta.get("required_parameters", ()))
    missing = sorted(required - names)
    accepted = not unknown and not missing
    declared = [{"name": name, "type": str(parameters[name].get("type", "unknown")),
                 "kind": str(parameters[name].get("kind", "unknown"))}
                for name in sorted(names & known)]
    signature = {"application": str(meta["app"]), "callable_name": str(meta["function_name"]),
                 "operation": operation, "declared_parameters": declared,
                 "access_mode": str(meta.get("access_mode", "unknown")),
                 "public_required": list(meta.get("required_parameters", ())),
                 "public_optional_present": sorted(names & set(meta.get("optional_parameters", ()))),
                 "runtime_context_present": sorted(names & context),
                 "output_slots": list(meta.get("output_slots", ())) }
    return {"schema_accepted": accepted,
            "schema_error": None if accepted else ("missing_public_required" if missing else "unknown_undeclared_field"),
            "missing_required": missing, "unknown_fields": unknown,
            "operation_signature": signature, "operation_signature_sha256": digest(signature),
            "invocation_value_hashes": value_hashes, "invocation_values_sha256": digest(values)}


class ExecutionEvidenceJournal:
    """Append-only, fsynced journal with duplicate/tamper detection."""

    def __init__(self, path: str | Path, *, require_e_backed: bool = True) -> None:
        self.path = normalize_evidence_path(path, require_e_backed=require_e_backed)
        self._seen: dict[tuple[str, int], str] = {}
        if self.path.exists():
            try:
                raw = self.path.read_bytes()
            except OSError as exc:
                raise JournalPathError("read", self.path, exc) from exc
            for line in raw.splitlines():
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError("incomplete execution evidence journal record") from exc
                event_hash = item.get("event_sha256")
                if event_hash != digest({key: value for key, value in item.items() if key != "event_sha256"}):
                    raise ValueError("execution evidence event hash mismatch")
                key = (str(item.get("parent_program_id")), int(item.get("monotonic_index")))
                if key in self._seen:
                    raise ValueError("duplicate execution evidence event")
                self._seen[key] = str(event_hash)

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        record = dict(event)
        record["event_sha256"] = digest(record)
        key = (str(record["parent_program_id"]), int(record["monotonic_index"]))
        prior = self._seen.get(key)
        if prior:
            if prior != record["event_sha256"]:
                raise ValueError("execution evidence duplicate conflicts with durable event")
            return record
        try:
            handle = self.path.open("a", encoding="utf-8")
        except OSError as exc:
            raise JournalPathError("open_append", self.path, exc) from exc
        try:
            payload = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        except (TypeError, ValueError, UnicodeError) as exc:
            raise JournalPathError("serialize", self.path, exc) from exc
        try:
            handle.write(payload)
        except OSError as exc:
            raise JournalPathError("write", self.path, exc) from exc
        try:
            handle.flush()
        except OSError as exc:
            raise JournalPathError("flush", self.path, exc) from exc
        try:
            os.fsync(handle.fileno())
        except OSError as exc:
            raise JournalPathError("fsync", self.path, exc) from exc
        finally:
            handle.close()
        self._seen[key] = record["event_sha256"]
        return record


class DispatcherEvidenceRecorder:
    """Wrap the shared AppWorld request dispatcher without changing its result."""

    def __init__(self, registry: Mapping[str, Any], journal: ExecutionEvidenceJournal,
                 parent_program_id: str, registry_sha256: str) -> None:
        if registry.get("registry_sha256") != registry_sha256:
            raise ValueError("frozen callable registry hash differs from worker configuration")
        _registry_index(registry)
        self.registry = dict(registry)
        self.journal = journal
        self.parent_program_id = parent_program_id
        self.registry_sha256 = registry_sha256
        self.index = 0
        # AppWorld temporarily replaces ``builtins.open`` and ``io.open``
        # while executing agent code.  A journal write inside the request
        # dispatcher would therefore be blocked as an unsafe agent-side file
        # operation.  We retain only value-redacted metadata in this private
        # per-action buffer and durably flush it after native execution
        # returns and AppWorld has restored its safety guard.
        self._pending: list[dict[str, Any]] = []

    def _queue(self, event: dict[str, Any]) -> None:
        self._pending.append(event)

    def flush(self) -> None:
        """Durably append the completed native program's ordered evidence."""
        while self._pending:
            event = self._pending[0]
            self.journal.append(event)
            self._pending.pop(0)

    def record_call(self, original: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        app_name = str(kwargs.get("_app_name", args[0] if args else ""))
        api_name = str(kwargs.get("_api_name", args[1] if len(args) > 1 else ""))
        data = {key: value for key, value in kwargs.items() if not key.startswith("_") and key not in {"client", "raise_on_failure", "track"}}
        metadata = _operation_record(self.registry, app_name, api_name, data)
        base = {"version": VERSION, "parent_program_id": self.parent_program_id,
                "monotonic_index": self.index, "callable_registry_sha256": self.registry_sha256,
                **metadata}
        self.index += 1
        try:
            response = original(*args, **kwargs)
        except BaseException as exc:
            self._queue({**base, "response_success": False,
                         "response_status": getattr(exc, "status_code", None), "response_error_class": type(exc).__name__,
                         "response_shape": {"kind": "exception"}, "response_sha256": None})
            raise
        status = getattr(response, "status_code", None)
        success = status == 200
        shape = _response_shape(response)
        outputs = _response_output_hashes(response, list(metadata["operation_signature"]["output_slots"])) if metadata["schema_accepted"] else {}
        self._queue({**base, "response_success": success, "response_status": status,
                     "response_error_class": None if success else f"http_{status}",
                     "response_shape": shape, "response_sha256": digest(shape), "response_output_value_hashes": outputs})
        return response

    def install(self, requester: Any) -> None:
        original = requester._request

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            return self.record_call(original, *args, **kwargs)

        requester._request = wrapped


def load_registry(path: str | Path, expected_sha256: str) -> dict[str, Any]:
    registry = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(registry, dict) or registry.get("registry_sha256") != expected_sha256:
        raise ValueError("frozen callable registry file/hash mismatch")
    _registry_index(registry)
    return registry


def normalize_evidence_path(value: str | Path, *, require_e_backed: bool = True) -> Path:
    """Convert an explicit Windows E: path or WSL path to a stable absolute path."""
    text = str(value).strip()
    # A Windows path must remain Windows-native in a Windows worker.  Mapping
    # it to ``/mnt/<drive>`` unconditionally turns it into a root-relative
    # path under ``pathlib.WindowsPath`` and breaks ordinary isolated fixtures.
    # POSIX workers use the WSL mapping so all durable run paths stay E-backed.
    if os.name == "posix" and len(text) >= 3 and text[1:3] in {":\\", ":/"}:
        drive = text[0].lower()
        text = f"/mnt/{drive}/" + text[3:].replace("\\", "/")
    path = Path(text)
    if not path.is_absolute():
        raise JournalPathError("path_not_absolute", path)
    try:
        resolved = path.resolve(strict=False)
    except OSError as exc:
        raise JournalPathError("resolve", path, exc) from exc
    if require_e_backed:
        e_backed = (str(resolved).startswith("/mnt/e/") if os.name == "posix"
                    else str(getattr(resolved, "drive", "")).lower() == "e:")
        if not e_backed:
            raise JournalPathError("not_e_backed", resolved)
    return resolved


def prepare_evidence_journal(path: str | Path, *, require_e_backed: bool = True) -> tuple[ExecutionEvidenceJournal, dict[str, Any]]:
    """Create/validate the parent and durability boundary before AppWorld starts."""
    resolved = normalize_evidence_path(path, require_e_backed=require_e_backed)
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise JournalPathError("mkdir_parent", resolved, exc) from exc
    # Zero-content preflight: opening, flushing, fsyncing, and a read-back all
    # occur before a task world exists.  No temporary/rename pattern is used
    # because an append-only record cannot be atomically replaced safely.
    try:
        with resolved.open("a+b") as handle:
            handle.flush(); os.fsync(handle.fileno())
        resolved.read_bytes()
    except OSError as exc:
        raise JournalPathError("preflight_open_fsync_read", resolved, exc) from exc
    journal = ExecutionEvidenceJournal(resolved, require_e_backed=require_e_backed)
    identity = {"resolved_path_kind": "wsl_e_backed_absolute" if require_e_backed else "test_absolute", "path_id": digest(str(resolved)),
                "path_identity_sha256": digest({"path": str(resolved), "device": resolved.stat().st_dev}),
                "version": VERSION}
    return journal, identity


def journal_records(path: str | Path, *, require_e_backed: bool = True) -> list[dict[str, Any]]:
    """Reload and verify every durable record without looking at task values."""
    journal = ExecutionEvidenceJournal(path, require_e_backed=require_e_backed)
    if not journal.path.exists():
        return []
    return [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]


def partition_v6_graph_evidence(records: list[Mapping[str, Any]], registry_sha256: str, *,
                                runtime_context_fields: frozenset[str] = frozenset(),
                                discard_schema_invalid_reads: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Separate callable evidence from immutable telemetry without renumbering.

    Lifecycle-independent audit rows carry no callable signature and are kept in
    the audit partition. Malformed or contradictory callable rows are rejected
    fail-closed rather than silently filtered.
    """
    eligible: list[dict[str, Any]]=[]; audit_only=[]; callable_errors=[]; rejected=[]; legacy_reclassified=[]; discarded_invalid_reads=[]
    for position,row in enumerate(records):
        signature=row.get("operation_signature")
        if not isinstance(signature, Mapping):
            audit_only.append({"position":position,"event_sha256":row.get("event_sha256"),"reason":"non_callable_audit_event"});continue
        if row.get("version") != VERSION or row.get("callable_registry_sha256") != registry_sha256:
            rejected.append({"position":position,"reason":"version_or_registry_mismatch"});continue
        if row.get("event_sha256") != digest({k:v for k,v in row.items() if k!="event_sha256"}):
            rejected.append({"position":position,"reason":"event_hash_mismatch"});continue
        if not row.get("schema_accepted"):
            # The first v6 acquisition emitted immutable evidence before the
            # dispatcher consumed the registry's global runtime-context list.
            # Reclassify only that narrow case; all other schema failures stay
            # fail-closed and the source journal is never modified.
            unknown = {str(value) for value in row.get("unknown_fields", ())}
            missing = {str(value) for value in row.get("missing_required", ())}
            # Old journals predate the read-transport classification above.
            # Reclassify only exact pagination fields on a recorded public read
            # operation; any write or any other undeclared field still fails.
            signature_access_mode = signature.get("access_mode")
            pagination_only = (unknown <= _READ_TRANSPORT_CONTEXT_FIELDS and signature_access_mode == "read")
            legacy_context_only = (row.get("schema_error") == "unknown_undeclared_field" and bool(unknown)
                                   and (unknown <= set(runtime_context_fields) or pagination_only) and not missing)
            if not legacy_context_only:
                # A native agent can make an unsuccessful or server-ignored
                # read call using a field outside the frozen callable schema.
                # It is never evidence: preserve a hash-bound audit entry and
                # omit it from the graph.  This narrow option is for isolated
                # acquisition only.  Writes and ordinary evaluation retain the
                # default fail-closed boundary.
                if discard_schema_invalid_reads and signature_access_mode == "read":
                    discarded_invalid_reads.append({"position": position, "event_sha256": row.get("event_sha256"),
                                                    "schema_error": row.get("schema_error"),
                                                    "response_success": bool(row.get("response_success"))})
                    audit_only.append({"position": position, "event_sha256": row.get("event_sha256"),
                                       "reason": "discarded_schema_invalid_read"})
                    continue
                rejected.append({"position":position,"reason":"schema_mismatch"});continue
            reclassified = dict(row)
            reclassified.update({"schema_accepted": True, "schema_error": None, "unknown_fields": [],
                                 "legacy_runtime_context_reclassification": {
                                     "version": "v6-runtime-context-reclassification-v1",
                                     "fields": sorted(unknown),
                                     "source_event_sha256": row.get("event_sha256"),
                                 }})
            row = reclassified
            legacy_reclassified.append({"position": position, "event_sha256": row.get("event_sha256"), "fields": sorted(unknown)})
        if not row.get("response_success"):
            callable_errors.append(dict(row));continue
        eligible.append(dict(row))
    if rejected: raise ValueError(f"v6 telemetry integrity rejection: {rejected[0]['reason']}")
    audit={"version":VERSION,"registry_sha256":registry_sha256,"total_rows":len(records),"eligible_rows":len(eligible),
           "audit_only_rows":len(audit_only),"callable_error_rows":len(callable_errors),"rejected_rows":len(rejected),
           "legacy_runtime_context_reclassified_rows":len(legacy_reclassified), "legacy_runtime_context_reclassified":legacy_reclassified,
           "discarded_schema_invalid_read_rows": len(discarded_invalid_reads),
           "discarded_schema_invalid_reads": discarded_invalid_reads,
           "eligible_sha256":digest(eligible),"audit_only_sha256":digest(audit_only),"callable_errors_sha256":digest(callable_errors),"records_sha256":digest(records)}
    return eligible,audit


def learning_events(records: list[Mapping[str, Any]], registry_sha256: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Project response-attested public events without exposing values.

    This is deliberately a projection of dispatcher evidence, never a parser
    for agent Python.  Any schema failure or unsuccessful response makes the
    returned audit invalid so task-boundary promotion fails closed.
    """
    events: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    prior: dict[str, int] = {}
    for row in records:
        if row.get("version") != VERSION or row.get("callable_registry_sha256") != registry_sha256:
            invalid.append({"reason": "version_or_registry_mismatch"}); continue
        expected = digest({key: value for key, value in row.items() if key != "event_sha256"})
        if row.get("event_sha256") != expected:
            invalid.append({"reason": "event_hash_mismatch"}); continue
        parent = str(row.get("parent_program_id")); index = row.get("monotonic_index")
        if not isinstance(index, int) or index != prior.get(parent, -1) + 1:
            invalid.append({"reason": "nonmonotonic_or_duplicate_event", "parent_program_id": parent}); continue
        prior[parent] = index
        signature = row.get("operation_signature")
        if not row.get("schema_accepted") or not row.get("response_success") or not isinstance(signature, Mapping):
            invalid.append({"reason": row.get("schema_error") or row.get("response_error_class") or "unattested_call",
                            "parent_program_id": parent, "monotonic_index": index})
            continue
        events.append({"operation": signature["operation"], "input_slots": list(signature["public_required"]),
                       "output_slots": list(signature["output_slots"]), "precondition": "",
                       "check": "native_public_response_attested", "parameters": {}, "observed": True,
                       "execution_event_sha256": row["event_sha256"]})
    audit = {"version": VERSION, "registry_sha256": registry_sha256,
             "event_count": len(records), "projected_count": len(events),
             "invalid": invalid, "valid": bool(records) and not invalid,
             "records_sha256": digest(list(records)), "events_sha256": digest(events)}
    return events, audit

