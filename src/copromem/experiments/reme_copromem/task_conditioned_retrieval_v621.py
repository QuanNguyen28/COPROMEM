"""Public, reproducible task-conditioned retrieval for CoProMem v6.2.1.

This boundary intentionally separates two kinds of evidence:

* A task query identifies public *terminal effects* which the visible task
  instruction supports.
* A committed semantic schema supplies the response-attested prerequisite
  procedure.  A user instruction is not required to list those prerequisites.

It never reads a task database, a scorer, an execution trace, or a memory-bank
while deriving a query.  The bank is consulted only by :func:`retrieve`.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any


POLICY_VERSION = "copromem-v6.2.1-task-conditioned-retrieval"
_TOKEN = re.compile(r"[a-z][a-z0-9_]{1,}")
_SPLIT = re.compile(r"[._-]+")
_GENERIC_ACTIONS = frozenset({"add", "create", "delete", "get", "remove", "search", "send", "show", "update"})
_NON_SEMANTIC_APPS = frozenset({"api_docs", "supervisor"})
_AUTH_RUNTIME_TERMS = frozenset({"auth", "authenticate", "authentication", "login", "log_in", "logout"})
_HTTP_ACTION_CLASSES = {
    "GET": frozenset({"get", "show", "search", "find", "list", "view", "read"}),
    "POST": frozenset({"create", "add", "send", "attach", "upload", "initiate", "make", "request"}),
    "PATCH": frozenset({"update", "edit", "modify", "change"}),
    "PUT": frozenset({"update", "edit", "modify", "change"}),
    "DELETE": frozenset({"delete", "remove", "clear"}),
}


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def frozen_policy() -> dict[str, Any]:
    """Return the content-addressed policy that must be frozen before tasks."""
    value = {
        "policy_version": POLICY_VERSION,
        "query_evidence": ["visible_instruction", "public_app_descriptions", "frozen_callable_registry"],
        "canonical_namespace_parser": "apis.<underscore_preserving_app>.<underscore_tokenized_callable>",
        "public_http_action_classes": {key: sorted(value) for key, value in sorted(_HTTP_ACTION_CLASSES.items())},
        "query_exclusions": ["hidden_state", "scorer", "current_or_future_actions", "task_answers", "task_specific_rules"],
        "compatibility_requirements": ["exact_registry_hash", "registry_declared_alias_only", "committed_v61_schema_only",
                                       "terminal_effect_in_public_query", "public_app_relevance", "positive_successes_at_least_2",
                                       "typed_public_constraints", "no_reversed_public_dependency", "no_infrastructure_auth_supervisor_operation"],
        "selection": "score descending then schema_id ascending",
        "guidance": "ordered_unique_schema_spine_with_audit_only_repeat_multiplicity_and_failure_precondition_warnings",
        "dynamic": "exact_durable_pre_task_prefix_only",
        "fixed": "read_only",
        "reproduction": "canonical_JSON_UTF8_SHA256_and_full_provenance_equality",
    }
    return {**value, "policy_sha256": digest(value)}


def _stem(token: str) -> str:
    """A deliberately small, task-independent English surface normalizer."""
    token = token.lower()
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 5 and token.endswith("ing"):
        token = token[:-3]
        return token[:-1] if len(token) > 2 and token[-1:] == token[-2:-1] else token
    if len(token) > 4 and token.endswith("ed"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(sorted({_stem(item) for item in _TOKEN.findall(text.lower())}))


def _operation_tokens(operation: str) -> tuple[str, str, tuple[str, ...]]:
    # AppWorld's canonical namespace is ``apis.<application>.<callable>``.
    # Application and callable names can themselves contain underscores; only
    # the two dots delimit namespace fields.  Splitting the full string on
    # underscores would turn ``simple_note`` into the nonexistent app
    # ``simple`` and corrupt public-app compatibility.
    raw = operation.lower().split(".", 2)
    if len(raw) != 3 or raw[0] != "apis" or not raw[1] or not raw[2]:
        raise ValueError("registry operation is not canonical")
    app, leaf = raw[1], tuple(_stem(item) for item in _SPLIT.split(raw[2]) if item)
    if not leaf:
        raise ValueError("registry operation has no callable name")
    return app, leaf[0], leaf[1:]


def _operation_index(registry: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    registry_hash = registry.get("registry_sha256")
    if not isinstance(registry_hash, str) or not registry_hash:
        raise ValueError("frozen callable registry identity required")
    rows = registry.get("operations")
    if not isinstance(rows, Sequence):
        raise ValueError("frozen callable registry has no operations")
    index: dict[str, Mapping[str, Any]] = {}
    for item in rows:
        if not isinstance(item, Mapping) or not isinstance(item.get("operation"), str):
            raise ValueError("malformed callable registry operation")
        operation = str(item["operation"])
        _operation_tokens(operation)
        if operation in index:
            raise ValueError("duplicate callable registry operation")
        index[operation] = item
    return index


def _aliases(registry: Mapping[str, Any], index: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    raw = registry.get("normalization", {}).get("operation_aliases", {})
    if not isinstance(raw, Mapping):
        raise ValueError("registry operation aliases are malformed")
    aliases = {str(alias): str(operation) for alias, operation in raw.items()}
    if any(operation not in index for operation in aliases.values()):
        raise ValueError("registry alias points to an unknown operation")
    return aliases


def canonical_operation(operation: str, registry: Mapping[str, Any]) -> str:
    index = _operation_index(registry)
    aliases = _aliases(registry, index)
    result = aliases.get(operation, operation)
    if result not in index:
        raise ValueError("operation is not declared by the frozen registry")
    return result


def derive_task_query(instruction: str, domain: str, public_tool_metadata: Mapping[str, Any],
                      callable_registry: Mapping[str, Any]) -> dict[str, Any]:
    """Derive an operation query from public pre-execution information only.

    An operation is supported by a verb plus at least one non-generic callable
    component present in the task instruction.  App names explicitly mentioned
    in the instruction narrow the candidate set; a generic tool catalogue does
    not itself claim that every app is task-relevant.
    """
    if not isinstance(instruction, str) or not isinstance(domain, str):
        raise ValueError("public instruction and domain are required")
    if not isinstance(public_tool_metadata, Mapping):
        raise ValueError("public tool metadata is required")
    index = _operation_index(callable_registry)
    aliases = _aliases(callable_registry, index)
    tokens = set(_tokens(instruction))
    catalog = public_tool_metadata.get("app_descriptions", {})
    if not isinstance(catalog, Mapping):
        raise ValueError("public app descriptions are required")
    public_apps = {str(name).lower() for name in catalog if isinstance(name, str)}
    named_apps = tuple(sorted(app for app in public_apps
                              if all(_stem(part) in tokens for part in app.split("_"))))
    matches: list[dict[str, Any]] = []
    for operation, meta in sorted(index.items()):
        app, verb, nouns = _operation_tokens(operation)
        if app in _NON_SEMANTIC_APPS or verb in _AUTH_RUNTIME_TERMS or any(noun in _AUTH_RUNTIME_TERMS for noun in nouns):
            continue
        if named_apps and app not in named_apps:
            continue
        noun_matches = sorted(set(nouns) & tokens)
        # A bare generic verb (for example, "show") is never enough to infer
        # an API operation.  A callable with only a verb needs an explicit app.
        action_terms = _HTTP_ACTION_CLASSES.get(str(meta.get("http_method") or "").upper(), frozenset({verb}))
        verb_match = verb in tokens or bool(action_terms & tokens)
        specific_nouns = [noun for noun in nouns if noun not in _GENERIC_ACTIONS]
        supported = verb_match and (bool(noun_matches) or (not specific_nouns and app in named_apps))
        if not supported:
            continue
        matches.append({"operation": operation, "app": app, "verb": verb,
                        "matched_nouns": noun_matches, "matched_action_terms": sorted(action_terms & tokens),
                        "match_strength": len(noun_matches) + int(app in named_apps),
                        "public_access_mode": str(meta.get("access_mode") or "unknown")})
    operations = [item["operation"] for item in matches]
    descriptor = {"domain": domain, "instruction_token_sha256": digest(sorted(tokens)),
                  "relevant_public_apps": list(named_apps), "candidate_operations": operations}
    record = {"policy_version": POLICY_VERSION,
              "instruction_sha256": hashlib.sha256(instruction.encode("utf-8")).hexdigest(),
              "public_tool_metadata_sha256": digest(public_tool_metadata),
              "callable_registry_sha256": str(callable_registry["registry_sha256"]),
              "alias_map_sha256": digest(aliases), "derived_public_descriptor": descriptor,
              # ``query_operations`` retains the maintained runner boundary;
              # the canonical name is explicit for v6.2.1 provenance.
              "canonical_query_operations": operations, "query_operations": operations,
              "operation_evidence": matches,
              "derivation_status": "specific" if operations else "empty_public_query",
              "derivation_reason": None if operations else "no public operation has both a supported action and semantic component"}
    record["query_sha256"] = digest(record)
    return record


def validate_task_query(record: Mapping[str, Any], *, instruction: str, public_tool_metadata: Mapping[str, Any],
                        callable_registry: Mapping[str, Any]) -> None:
    descriptor = record.get("derived_public_descriptor")
    if not isinstance(descriptor, Mapping):
        raise ValueError("task query has no public descriptor")
    expected = derive_task_query(instruction, str(descriptor.get("domain") or ""),
                                 public_tool_metadata, callable_registry)
    if dict(record) != expected:
        raise ValueError("task-query provenance does not reproduce from public inputs")


def _schema_rows(state: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows = state.get("contrastive_v6_schemas", {})
    if not isinstance(rows, Mapping):
        raise ValueError("semantic bank has no visible schema container")
    result: dict[str, Mapping[str, Any]] = {}
    for schema_id, schema in rows.items():
        if not isinstance(schema_id, str) or not isinstance(schema, Mapping):
            raise ValueError("semantic bank schema is malformed")
        # Candidate/audit containers are deliberately outside this retrieval
        # namespace.  A schema must be a committed semantic v6.1 record.
        if schema.get("policy_version") != "copromem-v6.1-semantic-graph-v1":
            continue
        result[schema_id] = schema
    return result


def _schema_features(schema_id: str, schema: Mapping[str, Any], query: Mapping[str, Any],
                     registry: Mapping[str, Any], index: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    query_ops = tuple(str(item) for item in query.get("canonical_query_operations", ()))
    descriptor = query.get("derived_public_descriptor", {})
    named_apps = set(descriptor.get("relevant_public_apps", ())) if isinstance(descriptor, Mapping) else set()
    required = tuple(str(item) for item in schema.get("required_operations", ()))
    terminal = str(schema.get("terminal_effect") or "")
    reasons: list[str] = []
    if schema.get("registry_sha256") != registry.get("registry_sha256"):
        reasons.append("registry_hash_mismatch")
    if not required:
        reasons.append("schema_has_no_required_operation")
    if not terminal or terminal not in required:
        reasons.append("schema_terminal_is_not_a_required_operation")
    unknown = [operation for operation in required if operation not in index]
    if unknown:
        reasons.append("schema_operation_not_in_registry")
    terminal_app = _operation_tokens(terminal)[0] if terminal in index else None
    if named_apps and terminal_app not in named_apps:
        reasons.append("terminal_app_not_publicly_relevant")
    if terminal not in query_ops:
        reasons.append("terminal_effect_not_supported_by_public_query")
    support = schema.get("support", {})
    if not isinstance(support, Mapping) or int(support.get("successes", 0)) < 2:
        reasons.append("insufficient_positive_success_support")
    typed = schema.get("typed_constraints", ())
    if not isinstance(typed, Sequence):
        reasons.append("schema_typed_constraints_malformed")
    # Required operations are learned prerequisites, not a hidden condition on
    # the instruction.  Validate their public declarations but never require
    # them to appear in the task wording.
    declared_dependencies = {(str(edge.get("from_operation")), str(edge.get("to_operation")))
                             for edge in registry.get("dependency_edges", ()) if isinstance(edge, Mapping)}
    adjacent = list(zip(required, required[1:]))
    public_edge_count = sum((left, right) in declared_dependencies for left, right in adjacent)
    reversed_edges = [(left, right) for left, right in adjacent
                      if (right, left) in declared_dependencies and (left, right) not in declared_dependencies]
    if reversed_edges:
        reasons.append("schema_has_reversed_public_dependency")
    operation_apps = {_operation_tokens(operation)[0] for operation in required if operation in index}
    nonsemantic = []
    for operation in required:
        if operation not in index:
            continue
        app, verb, nouns = _operation_tokens(operation)
        if app in _NON_SEMANTIC_APPS or verb in _AUTH_RUNTIME_TERMS or any(noun in _AUTH_RUNTIME_TERMS for noun in nouns):
            nonsemantic.append(operation)
    nonsemantic.sort()
    if nonsemantic:
        reasons.append("schema_contains_nonsemantic_infrastructure_or_auth_operation")
    typed_by_operation = {str(item.get("operation")): item for item in typed if isinstance(item, Mapping)} if isinstance(typed, Sequence) else {}
    missing_typed = [operation for operation in required if operation not in typed_by_operation]
    if missing_typed:
        reasons.append("schema_missing_typed_public_constraint")
    produced: set[str] = set(); dependency_checks: list[dict[str, Any]] = []
    for operation in required:
        constraint = typed_by_operation.get(operation, {})
        needs = tuple(str(value) for value in constraint.get("required", ()) if isinstance(value, str)) if isinstance(constraint, Mapping) else ()
        external = [slot for slot in needs if slot not in produced]
        dependency_checks.append({"operation": operation, "required_inputs": list(needs),
                                  "satisfied_by_prior_schema_output": sorted(set(needs) & produced),
                                  "external_public_inputs": external})
        if isinstance(constraint, Mapping):
            produced.update(str(value) for value in constraint.get("outputs", ()) if isinstance(value, str))
    failure_counts = support.get("failure_counts", {}) if isinstance(support, Mapping) else {}
    warnings = sorted(operation for operation, count in failure_counts.items() if int(count) > 0 and operation in required) if isinstance(failure_counts, Mapping) else []
    compatible = not reasons
    return {"schema_id": schema_id, "compatible": compatible, "rejection_reason": None if compatible else reasons[0],
            "rejection_reasons": reasons, "terminal_effect": terminal,
            "terminal_effect_supported": terminal in query_ops, "terminal_app": terminal_app,
            "required_operations": list(required), "required_operation_count": len(required),
            "schema_operation_apps": sorted(operation_apps), "nonsemantic_operations": nonsemantic,
            "missing_typed_constraints": missing_typed, "reversed_public_dependencies": [list(edge) for edge in reversed_edges],
            "public_dependency_edge_count": public_edge_count, "dependency_input_checks": dependency_checks,
            "positive_success_count": int(support.get("successes", 0)) if isinstance(support, Mapping) else 0,
            "negative_failure_count": int(support.get("failures", 0)) if isinstance(support, Mapping) else 0,
            "failure_operation_warnings": warnings,
            "score": (1000 + 10 * int(terminal_app in named_apps) + int(support.get("successes", 0))) if compatible else 0}


def _guidance(schema_id: str, schema: Mapping[str, Any], features: Mapping[str, Any]) -> str:
    typed = {str(item.get("operation")): item for item in schema.get("typed_constraints", ()) if isinstance(item, Mapping)}
    occurrences: dict[str, int] = {}
    ordered_unique: list[str] = []
    for operation in features["required_operations"]:
        occurrences[operation] = occurrences.get(operation, 0) + 1
        if operation not in ordered_unique:
            ordered_unique.append(operation)
    lines = [f"# Retrieved response-attested schema: {schema_id}",
             f"Terminal public effect: {features['terminal_effect']}"]
    # A loop in a source trajectory is evidence of multiplicity, not an
    # instruction to mechanically repeat an API call.  Render the ordered
    # semantic spine once, retain multiplicities below, and never fabricate a
    # dataflow distinction that the frozen schema did not preserve.
    for position, operation in enumerate(ordered_unique, 1):
        constraint = typed.get(operation, {})
        fields = ", ".join(str(item) for item in constraint.get("required", ())) or "no declared public input"
        outputs = ", ".join(str(item) for item in constraint.get("outputs", ())) or "no declared public output"
        lines.append(f"{position}. {operation}; public inputs: {fields}; public outputs: {outputs}.")
    repeated = [f"{operation} x{count}" for operation, count in occurrences.items() if count > 1]
    if repeated:
        lines.append("Observed call multiplicity (audit-only; do not repeat without response-attested dataflow): " + "; ".join(repeated) + ".")
    for operation in features["failure_operation_warnings"]:
        lines.append(f"Caution: response-attested failure evidence exists for {operation}; verify its public preconditions.")
    return "\n".join(lines)


def retrieve(state: Mapping[str, Any], task_query: Mapping[str, Any], callable_registry: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """Select one committed, public-effect-compatible schema deterministically."""
    if task_query.get("callable_registry_sha256") != callable_registry.get("registry_sha256"):
        raise ValueError("task query registry identity mismatch")
    index = _operation_index(callable_registry)
    schemas = _schema_rows(state)
    features = [_schema_features(schema_id, schema, task_query, callable_registry, index)
                for schema_id, schema in sorted(schemas.items())]
    compatible = sorted((item for item in features if item["compatible"]),
                        key=lambda item: (-int(item["score"]), str(item["schema_id"])))
    selected = compatible[0] if compatible else None
    guidance = "" if selected is None else _guidance(str(selected["schema_id"]), schemas[str(selected["schema_id"])], selected)
    provenance = {"policy_version": POLICY_VERSION, "policy_sha256": frozen_policy()["policy_sha256"],
                  "pre_state_semantic_sha256": digest(state),
                  "task_query": dict(task_query), "task_query_sha256": str(task_query.get("query_sha256") or ""),
                  "registry_sha256": str(callable_registry["registry_sha256"]),
                  "candidate_schema_ids": [item["schema_id"] for item in features],
                  "candidate_scores": features, "selected_schema_id": None if selected is None else selected["schema_id"],
                  "selected_schema_ids": [] if selected is None else [selected["schema_id"]],
                  "fallback_category": "empty_insufficient_public_evidence" if not guidance else "learned_schema",
                  "fallback_reason": ("no committed schema passed terminal-effect, registry, and support checks" if not guidance else None),
                  "guidance_sha256": digest(guidance), "guidance_nonempty": bool(guidance),
                  "prompt_injection_sha256": digest(guidance),
                  "reproduction_version": POLICY_VERSION}
    provenance["retrieval_sha256"] = digest(provenance)
    return guidance, provenance


def reproduce_retrieval(state: Mapping[str, Any], task_query: Mapping[str, Any], callable_registry: Mapping[str, Any],
                         provenance: Mapping[str, Any]) -> str:
    if digest(state) != provenance.get("pre_state_semantic_sha256"):
        raise ValueError("retrieval pre-state mismatch")
    if dict(task_query) != provenance.get("task_query") or task_query.get("query_sha256") != provenance.get("task_query_sha256"):
        raise ValueError("retrieval query mismatch")
    guidance, expected = retrieve(state, task_query, callable_registry)
    if dict(provenance) != expected:
        raise ValueError("retrieval provenance mismatch")
    return guidance
