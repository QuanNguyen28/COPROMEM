from __future__ import annotations

import copy

import pytest

from copromem.experiments.reme_copromem.task_conditioned_retrieval_v621 import (
    derive_task_query,
    digest,
    frozen_policy,
    reproduce_retrieval,
    retrieve,
    validate_task_query,
)


REGISTRY = {
    "registry_sha256": "registry-v621-fixture",
    "normalization": {"operation_aliases": {"spotify__update_playlist": "apis.spotify.update_playlist"}},
    "operations": [
        {"operation": "apis.spotify.show_playlist", "app": "spotify", "access_mode": "read"},
        {"operation": "apis.spotify.update_playlist", "app": "spotify", "access_mode": "write"},
        {"operation": "apis.venmo.create_transaction", "app": "venmo", "access_mode": "write"},
    ],
    "dependency_edges": [{"from_operation": "apis.spotify.show_playlist", "to_operation": "apis.spotify.update_playlist", "via_slot": "playlist_id"}],
}
META = {"app_descriptions": {"spotify": "public Spotify APIs", "venmo": "public Venmo APIs"}}


def _schema(*, terminal: str = "apis.spotify.update_playlist", successes: int = 2, failures: int = 0):
    required = ["apis.spotify.show_playlist", terminal]
    return {"policy_version": "copromem-v6.1-semantic-graph-v1", "registry_sha256": REGISTRY["registry_sha256"],
            "required_operations": required, "terminal_effect": terminal,
            "typed_constraints": [{"operation": "apis.spotify.show_playlist", "required": [], "outputs": ["playlist_id"]},
                                  {"operation": terminal, "required": ["playlist_id"], "outputs": ["message"]}],
            "support": {"successes": successes, "failures": failures,
                        "failure_counts": {terminal: failures} if failures else {}}}


def _state():
    return {"state_format": "copromem-v6.1-semantic-state-v1", "contrastive_v6_schemas": {
        "schema_spotify": _schema(), "schema_venmo": {**_schema(terminal="apis.venmo.create_transaction"),
        "required_operations": ["apis.venmo.create_transaction"], "typed_constraints": [],
        }}}


def test_compatible_task_selects_schema_and_renders_schema_content():
    query = derive_task_query("Please update the Spotify playlist", "appworld", META, REGISTRY)
    guidance, provenance = retrieve(_state(), query, REGISTRY)
    assert query["derivation_status"] == "specific"
    assert provenance["selected_schema_id"] == "schema_spotify"
    assert "apis.spotify.show_playlist" in guidance and "apis.spotify.update_playlist" in guidance
    assert provenance["guidance_nonempty"] and provenance["prompt_injection_sha256"] == digest(guidance)
    assert provenance["policy_sha256"] == frozen_policy()["policy_sha256"]


def test_registry_supported_alternative_path_and_aliases_stay_canonical():
    query = derive_task_query("Update Spotify playlists", "appworld", META, REGISTRY)
    assert query["canonical_query_operations"] == ["apis.spotify.update_playlist"]
    validate_task_query(query, instruction="Update Spotify playlists", public_tool_metadata=META, callable_registry=REGISTRY)


def test_underscore_containing_app_namespace_remains_canonical():
    registry = {**REGISTRY, "normalization": {"operation_aliases": {}}, "operations": [
        {"operation": "apis.simple_note.update_note", "app": "simple_note", "access_mode": "write"},
    ]}
    query = derive_task_query("Update a simple note", "appworld", {"app_descriptions": {"simple_note": "public"}}, registry)
    assert query["derived_public_descriptor"]["relevant_public_apps"] == ["simple_note"]
    assert query["canonical_query_operations"] == ["apis.simple_note.update_note"]


def test_public_http_action_class_recognizes_edit_for_patch_without_an_operation_alias():
    registry = {**REGISTRY, "normalization": {"operation_aliases": {}}, "operations": [
        {"operation": "apis.simple_note.update_note", "app": "simple_note", "access_mode": "write", "http_method": "PATCH"},
    ]}
    query = derive_task_query("Edit a simple note", "appworld", {"app_descriptions": {"simple_note": "public"}}, registry)
    assert query["canonical_query_operations"] == ["apis.simple_note.update_note"]
    assert query["operation_evidence"][0]["matched_action_terms"] == ["edit"]


def test_authentication_and_supervisor_operations_never_enter_a_public_query():
    registry = {"registry_sha256": "roles", "normalization": {"operation_aliases": {}}, "operations": [
        {"operation": "apis.spotify.login", "app": "spotify", "http_method": "POST"},
        {"operation": "apis.supervisor.complete_task", "app": "supervisor", "http_method": "POST"},
    ], "dependency_edges": []}
    query = derive_task_query("Login to Spotify and complete task", "appworld", {"app_descriptions": {"spotify": "public", "supervisor": "public"}}, registry)
    assert query["derivation_status"] == "empty_public_query"


def test_alternative_schema_path_is_eligible_without_requiring_hidden_prerequisites():
    state = {"contrastive_v6_schemas": {
        "schema_a": _schema(),
        "schema_b": {**_schema(), "required_operations": ["apis.spotify.update_playlist"],
                     "typed_constraints": [{"operation": "apis.spotify.update_playlist", "required": [], "outputs": ["message"]}]},
    }}
    query = derive_task_query("Update Spotify playlist", "appworld", META, REGISTRY)
    guidance, provenance = retrieve(state, query, REGISTRY)
    assert provenance["selected_schema_id"] == "schema_a"  # deterministic schema-ID tie break
    assert "show_playlist" in guidance


def test_same_task_trials_share_frozen_pre_state_and_committed_change_only_affects_future_state():
    frozen = _state()
    query = derive_task_query("Please update the Spotify playlist", "appworld", META, REGISTRY)
    left = retrieve(frozen, query, REGISTRY)
    right = retrieve(frozen, query, REGISTRY)
    assert left == right and digest(frozen) == left[1]["pre_state_semantic_sha256"]
    committed_future = copy.deepcopy(frozen)
    committed_future["contrastive_v6_schemas"]["schema_new"] = _schema()
    assert digest(committed_future) != digest(frozen)
    assert retrieve(frozen, query, REGISTRY) == left


def test_nonempty_and_empty_guidance_have_distinct_prompt_injection_identities():
    query = derive_task_query("Please update the Spotify playlist", "appworld", META, REGISTRY)
    guidance, selected = retrieve(_state(), query, REGISTRY)
    empty, rejected = retrieve(_state(), derive_task_query("Please show this", "appworld", META, REGISTRY), REGISTRY)
    assert guidance and selected["prompt_injection_sha256"] == digest(guidance)
    assert empty == "" and rejected["prompt_injection_sha256"] == digest("")
    assert selected["prompt_injection_sha256"] != rejected["prompt_injection_sha256"]


def test_irrelevant_schema_is_rejected_at_terminal_effect_predicate():
    query = derive_task_query("Please update the Spotify playlist", "appworld", META, REGISTRY)
    _, provenance = retrieve({"contrastive_v6_schemas": {"schema_venmo": _state()["contrastive_v6_schemas"]["schema_venmo"]}}, query, REGISTRY)
    candidate = provenance["candidate_scores"][0]
    assert candidate["rejection_reason"] == "terminal_app_not_publicly_relevant"


def test_ambiguous_or_unsupported_public_evidence_fails_closed():
    query = derive_task_query("Please show this", "appworld", META, REGISTRY)
    guidance, provenance = retrieve(_state(), query, REGISTRY)
    assert query["derivation_status"] == "empty_public_query"
    assert not guidance and provenance["selected_schema_id"] is None


def test_failure_evidence_adds_constraint_without_replacing_success_procedure():
    state = {"contrastive_v6_schemas": {"schema_spotify": _schema(failures=1)}}
    query = derive_task_query("Please update the Spotify playlist", "appworld", META, REGISTRY)
    guidance, provenance = retrieve(state, query, REGISTRY)
    assert provenance["selected_schema_id"] == "schema_spotify"
    assert "Caution:" in guidance and "show_playlist" in guidance


def test_failure_only_schema_is_not_positive_guidance():
    state = {"contrastive_v6_schemas": {"schema_spotify": _schema(successes=1)}}
    query = derive_task_query("Please update the Spotify playlist", "appworld", META, REGISTRY)
    guidance, provenance = retrieve(state, query, REGISTRY)
    assert not guidance
    assert provenance["candidate_scores"][0]["rejection_reason"] == "insufficient_positive_success_support"


def test_semantic_relevance_rejects_reversed_dependencies_and_infrastructure_only_schemas():
    registry = {**REGISTRY, "operations": [
        {"operation": "apis.spotify.show_playlist", "app": "spotify", "access_mode": "read"},
        {"operation": "apis.spotify.update_playlist", "app": "spotify", "access_mode": "write"},
        {"operation": "apis.api_docs.show_endpoint", "app": "api_docs", "access_mode": "read"},
    ], "dependency_edges": [{"from_operation": "apis.spotify.show_playlist", "to_operation": "apis.spotify.update_playlist"}]}
    query = derive_task_query("Update Spotify playlist", "appworld", META, registry)
    reversed_schema = _schema(); reversed_schema["required_operations"] = ["apis.spotify.update_playlist", "apis.spotify.show_playlist"]
    reversed_schema["typed_constraints"] = [
        {"operation": "apis.spotify.update_playlist", "required": [], "outputs": ["message"]},
        {"operation": "apis.spotify.show_playlist", "required": [], "outputs": ["playlist_id"]},
    ]
    infra = _schema(terminal="apis.api_docs.show_endpoint")
    infra["required_operations"] = ["apis.api_docs.show_endpoint"]
    infra["typed_constraints"] = [{"operation": "apis.api_docs.show_endpoint", "required": [], "outputs": []}]
    _, provenance = retrieve({"contrastive_v6_schemas": {"reversed": reversed_schema, "infra": infra}}, query, registry)
    reasons = {item["schema_id"]: item["rejection_reason"] for item in provenance["candidate_scores"]}
    assert reasons["reversed"] == "schema_has_reversed_public_dependency"
    assert reasons["infra"] == "terminal_app_not_publicly_relevant"
    docs_query = derive_task_query("Show the api docs endpoint", "appworld", {"app_descriptions": {"api_docs": "public"}}, registry)
    _, docs_provenance = retrieve({"contrastive_v6_schemas": {"infra": infra}}, docs_query, registry)
    # Public documentation infrastructure is deliberately excluded before
    # scoring.  The candidate therefore cannot satisfy a public terminal
    # effect, which is stricter than admitting an infrastructure-only schema.
    assert docs_query["derivation_status"] == "empty_public_query"
    assert docs_provenance["candidate_scores"][0]["rejection_reason"] == "terminal_effect_not_supported_by_public_query"


def test_fixed_retrieval_does_not_mutate_and_dynamic_visibility_requires_committed_schema():
    fixed = _state(); dynamic = copy.deepcopy(fixed); before = digest(fixed)
    query = derive_task_query("Please update the Spotify playlist", "appworld", META, REGISTRY)
    retrieve(fixed, query, REGISTRY)
    assert digest(fixed) == before
    dynamic["candidate_audit"] = {"schema_future": _schema()}
    _, provenance = retrieve(dynamic, query, REGISTRY)
    assert "schema_future" not in provenance["candidate_schema_ids"]
    dynamic["contrastive_v6_schemas"]["schema_future"] = _schema()
    _, after = retrieve(dynamic, query, REGISTRY)
    assert "schema_future" in after["candidate_schema_ids"]


def test_reproduction_and_tampering_fail_closed():
    state = _state(); query = derive_task_query("Please update the Spotify playlist", "appworld", META, REGISTRY)
    guidance, provenance = retrieve(state, query, REGISTRY)
    assert reproduce_retrieval(state, query, REGISTRY, provenance) == guidance
    tampered = dict(provenance); tampered["guidance_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        reproduce_retrieval(state, query, REGISTRY, tampered)
    with pytest.raises(ValueError):
        retrieve(state, query, {**REGISTRY, "registry_sha256": "wrong"})


def test_concrete_values_do_not_enter_query_or_guidance():
    query = derive_task_query("Update Spotify playlist called Secret-123", "appworld", META, REGISTRY)
    guidance, _ = retrieve(_state(), query, REGISTRY)
    assert "Secret" not in str(query) and "123" not in guidance
