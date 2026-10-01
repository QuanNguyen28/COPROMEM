from __future__ import annotations

import copy
import pytest

from copromem.experiments.reme_copromem import task_conditioned_retrieval_v621 as v621
from copromem.experiments.reme_copromem import task_conditioned_retrieval_v622 as v622
from copromem.experiments.reme_copromem.runner import _copromem_prompt_memory_text, model_visible_memory_binding
from copromem.contrastive_graph_v6 import Graph, commit, digest
from copromem.semantic_spine_v622 import plan as semantic_spine_plan, validate as validate_semantic_spine, commit as commit_semantic_spine


REGISTRY = {
    "registry_sha256": "public-registry", "normalization": {"operation_aliases": {}},
    "operations": [
        {"operation": "apis.music.search_artist", "http_method": "GET"},
        {"operation": "apis.music.follow_artist", "http_method": "POST"},
        {"operation": "apis.notes.create_note", "http_method": "POST"},
        {"operation": "apis.docs.browse", "http_method": "GET"},
        {"operation": "apis.venmo.create_transaction", "http_method": "POST"},
    ],
    "dependency_edges": [
        {"from_operation": "apis.music.search_artist", "to_operation": "apis.music.follow_artist"},
    ],
}
QUERY = {
    "callable_registry_sha256": "public-registry", "query_sha256": "query",
    "canonical_query_operations": ["apis.music.follow_artist"],
    "derived_public_descriptor": {"relevant_public_apps": ["music"]},
}


def _schema(*, required, schema_id="schema", successes=2):
    counts = {}
    terminal_occurrence_id = None
    for operation in required:
        counts[operation] = counts.get(operation, 0) + 1
        if operation == "apis.music.follow_artist":
            terminal_occurrence_id = f"{operation}#{counts[operation]}"
    edges = []
    if "apis.music.search_artist" in required and "apis.music.follow_artist" in required:
        edges = [{"from_occurrence_id": "apis.music.search_artist#1",
                  "to_occurrence_id": "apis.music.follow_artist#1",
                  "producer_slot": "artist_id", "consumer_slot": "artist_id",
                  "attestation": "redacted_value_equality_in_every_success"}]
    templates = {
        "apis.docs.browse": {"required": [], "outputs": ["documentation"]},
        "apis.music.search_artist": {"required": [], "outputs": ["artist_id"]},
        "apis.music.follow_artist": {"required": ["artist_id"], "outputs": ["followed"]},
        "apis.venmo.create_transaction": {"required": [], "outputs": ["transaction_id"]},
    }
    typed = [{"operation": operation, "occurrence_index": position, **templates[operation]}
             for position, operation in enumerate(required, 1)]
    return schema_id, {
        "policy_version": "copromem-v6.1-semantic-graph-v1", "registry_sha256": "public-registry",
        "required_operations": required, "terminal_effect": "apis.music.follow_artist",
        "typed_constraints": typed, "terminal_occurrence_id": terminal_occurrence_id,
        "attested_dataflow_edges": edges,
        "support": {"successes": successes, "failures": 0, "failure_counts": {}},
    }


def _state(*schemas):
    return {"contrastive_v6_schemas": dict(schemas)}


def test_v622_filters_irrelevant_preconditions_but_preserves_transitive_public_path():
    guidance, provenance = v622.retrieve(_state(_schema(required=["apis.docs.browse", "apis.music.search_artist", "apis.music.follow_artist"])), QUERY, REGISTRY)
    projection = provenance["candidate_scores"][0]["semantic_projection"]
    assert [row["operation"] for row in projection["occurrences"]] == ["apis.music.search_artist", "apis.music.follow_artist"]
    assert projection["excluded_occurrences"][0]["operation"] == "apis.docs.browse"
    assert "apis.docs.browse" not in guidance
    assert "apis.music.search_artist" in guidance and "apis.music.follow_artist" in guidance
    assert v622.reproduce_retrieval(_state(_schema(required=["apis.docs.browse", "apis.music.search_artist", "apis.music.follow_artist"])), QUERY, REGISTRY, provenance) == guidance


def test_v622_preserves_identical_occurrences_and_order_to_model_visible_prompt():
    _, schema = _schema(required=["apis.music.search_artist", "apis.music.search_artist", "apis.music.follow_artist"])
    # Repeated identical operation content has distinct occurrence identities:
    # both searches provide independently required public inputs.
    schema["typed_constraints"] = [
        {"operation": "apis.music.search_artist", "occurrence_index": 1, "required": [], "outputs": ["artist_id_1"]},
        {"operation": "apis.music.search_artist", "occurrence_index": 2, "required": [], "outputs": ["artist_id_2"]},
        {"operation": "apis.music.follow_artist", "occurrence_index": 3, "required": ["artist_id_1", "artist_id_2"], "outputs": ["followed"]},
    ]
    schema["attested_dataflow_edges"] = [
        {"from_occurrence_id": "apis.music.search_artist#1", "to_occurrence_id": "apis.music.follow_artist#1",
         "producer_slot": "artist_id_1", "consumer_slot": "artist_id_1",
         "attestation": "redacted_value_equality_in_every_success"},
        {"from_occurrence_id": "apis.music.search_artist#2", "to_occurrence_id": "apis.music.follow_artist#1",
         "producer_slot": "artist_id_2", "consumer_slot": "artist_id_2",
         "attestation": "redacted_value_equality_in_every_success"},
    ]
    guidance, provenance = v622.retrieve(_state(("repeated", schema)), QUERY, REGISTRY)
    assert "[apis.music.search_artist#1]" in guidance
    assert "[apis.music.search_artist#2]" in guidance
    assert (guidance.index("[apis.music.search_artist#1]")
            < guidance.index("[apis.music.search_artist#2]")
            < guidance.index("[apis.music.follow_artist#1]"))
    slot = _copromem_prompt_memory_text(guidance)
    messages = [{"role": "user", "content": "prefix\n" + slot + "suffix\nΔ"}]
    binding = model_visible_memory_binding(messages, guidance)
    assert binding["injected_memory_visible_in_initial_prompt"] is True
    assert provenance["guidance_nonempty"] is True


def test_v622_semantic_tie_abstains_independently_of_schema_ids_and_input_order():
    a_id, a = _schema(required=["apis.music.search_artist", "apis.music.follow_artist"], schema_id="schema_z")
    b_id, b = _schema(required=["apis.music.search_artist", "apis.music.follow_artist"], schema_id="schema_a")
    state = _state((a_id, a), (b_id, b))
    guidance, provenance = v622.retrieve(state, QUERY, REGISTRY)
    reordered = _state((b_id, b), (a_id, a))
    second, reproduced = v622.retrieve(reordered, QUERY, REGISTRY)
    assert guidance == second == ""
    assert provenance["selection_decision"] == reproduced["selection_decision"] == "semantic_tie_abstention"
    assert provenance["selected_schema_id"] is None and reproduced["selected_schema_id"] is None


def test_v622_success_count_cannot_break_a_task_semantic_tie():
    weak_id, weak = _schema(required=["apis.music.search_artist", "apis.music.follow_artist"], schema_id="schema_a", successes=2)
    strong_id, strong = _schema(required=["apis.music.search_artist", "apis.music.follow_artist"], schema_id="schema_z", successes=3)
    guidance, provenance = v622.retrieve(_state((weak_id, weak), (strong_id, strong)), QUERY, REGISTRY)
    assert guidance == "" and provenance["selected_schema_id"] is None
    assert provenance["selection_decision"] == "semantic_tie_abstention"
    # The frozen v6.2.1 policy remains byte-for-byte its own method identity;
    # the new semantic-spine policy is not an implicit replacement.
    assert v621.POLICY_VERSION == "copromem-v6.2.1-task-conditioned-retrieval"
    assert v622.POLICY_VERSION != v621.POLICY_VERSION
    assert v621.frozen_policy()["guidance"].startswith("ordered_unique")
    assert v622.frozen_policy()["selection"] == "unique_semantic_evidence_winner_or_empty_guidance"


def test_repeated_query_matched_operation_does_not_win_by_multiplicity():
    one_id, one = _schema(required=["apis.music.search_artist", "apis.music.follow_artist"], schema_id="one")
    two_id, two = _schema(required=["apis.music.search_artist", "apis.music.search_artist",
                                      "apis.music.follow_artist"], schema_id="two")
    two["typed_constraints"] = [
        {"operation": "apis.music.search_artist", "occurrence_index": 1, "required": [], "outputs": ["artist_id"]},
        {"operation": "apis.music.search_artist", "occurrence_index": 2, "required": [], "outputs": ["artist_id"]},
        {"operation": "apis.music.follow_artist", "occurrence_index": 3, "required": ["artist_id"], "outputs": ["followed"]},
    ]
    query = {**QUERY, "canonical_query_operations": ["apis.music.search_artist", "apis.music.follow_artist"]}
    guidance, provenance = v622.retrieve(_state((one_id, one), (two_id, two)), query, REGISTRY)
    assert guidance == "" and provenance["selection_decision"] == "semantic_tie_abstention"
    assert [candidate["semantic_evidence"] for candidate in provenance["candidate_scores"]] == [[1], [1]]


def test_v622_unique_public_operation_match_can_select_without_schema_id_order():
    generic_id, generic = _schema(required=["apis.music.follow_artist"], schema_id="schema_a")
    specific_id, specific = _schema(required=["apis.music.search_artist", "apis.music.follow_artist"], schema_id="schema_z")
    query = {**QUERY, "canonical_query_operations": ["apis.music.search_artist", "apis.music.follow_artist"]}
    guidance, provenance = v622.retrieve(_state((generic_id, generic), (specific_id, specific)), query, REGISTRY)
    assert guidance and provenance["selected_schema_id"] == "schema_z"
    assert provenance["candidate_scores"][1]["semantic_evidence"] == [1]


def test_v622_excludes_unrelated_venmo_step_from_spotify_prompt():
    _, schema = _schema(required=["apis.venmo.create_transaction", "apis.music.follow_artist"])
    schema["typed_constraints"] = [
        {"operation": "apis.venmo.create_transaction", "required": [], "outputs": ["transaction_id"]},
        {"operation": "apis.music.follow_artist", "required": [], "outputs": ["followed"]},
    ]
    old_guidance, _ = v621.retrieve(_state(("mixed", schema)), QUERY, REGISTRY)
    assert "apis.venmo.create_transaction" in old_guidance
    guidance, provenance = v622.retrieve(_state(("mixed", schema)), QUERY, REGISTRY)
    assert guidance and "apis.venmo.create_transaction" not in guidance
    assert [row["operation"] for row in provenance["candidate_scores"][0]["semantic_projection"]["occurrences"]] == [
        "apis.music.follow_artist"]


def test_v622_same_named_slot_cannot_invent_cross_app_dataflow():
    _, schema = _schema(required=["apis.venmo.create_transaction", "apis.music.follow_artist"])
    schema["typed_constraints"] = [
        {"operation": "apis.venmo.create_transaction", "required": [], "outputs": ["artist_id"]},
        {"operation": "apis.music.follow_artist", "required": ["artist_id"], "outputs": ["followed"]},
    ]
    guidance, provenance = v622.retrieve(_state(("mixed", schema)), QUERY, REGISTRY)
    assert guidance and "apis.venmo.create_transaction" not in guidance
    assert provenance["candidate_scores"][0]["semantic_projection"]["dataflow_edges"] == []


def test_spotify_playlist_query_never_injects_venmo_transaction_prerequisite():
    registry = {
        "registry_sha256": "public-registry", "normalization": {"operation_aliases": {}},
        "operations": [
            {"operation": "apis.spotify.update_playlist", "http_method": "POST"},
            {"operation": "apis.venmo.create_transaction", "http_method": "POST"},
        ], "dependency_edges": [],
    }
    metadata = {"app_descriptions": {"spotify": "public", "venmo": "public"}}
    query = v622.derive_task_query("Please update the Spotify playlist", "appworld", metadata, registry)
    v622.validate_task_query(query, instruction="Please update the Spotify playlist",
                             public_tool_metadata=metadata, callable_registry=registry)
    schema = {"policy_version": "copromem-v6.1-semantic-graph-v1", "registry_sha256": "public-registry",
              "required_operations": ["apis.venmo.create_transaction", "apis.spotify.update_playlist"],
              "terminal_effect": "apis.spotify.update_playlist", "typed_constraints": [
                  {"operation": "apis.venmo.create_transaction", "required": [], "outputs": ["transaction_id"]},
                  {"operation": "apis.spotify.update_playlist", "required": ["playlist_id"], "outputs": ["playlist"]}],
              "support": {"successes": 2, "failures": 0, "failure_counts": {}}}
    state = _state(("mixed", schema))
    old_guidance, _ = v621.retrieve(state, query, registry)
    assert "apis.venmo.create_transaction" in old_guidance
    guidance, provenance = v622.retrieve(state, query, registry)
    assert guidance and "apis.venmo.create_transaction" not in guidance
    assert "verify current-task values for external inputs before use: playlist_id" in guidance
    assert v622.reproduce_retrieval(state, query, registry, provenance) == guidance


def test_v622_declared_cross_app_prerequisite_without_task_app_support_abstains():
    registry = copy.deepcopy(REGISTRY)
    registry["dependency_edges"].append({"from_operation": "apis.venmo.create_transaction",
                                         "to_operation": "apis.music.follow_artist"})
    _, schema = _schema(required=["apis.venmo.create_transaction", "apis.music.follow_artist"])
    schema["typed_constraints"] = [
        {"operation": "apis.venmo.create_transaction", "required": [], "outputs": ["artist_id"]},
        {"operation": "apis.music.follow_artist", "required": ["artist_id"], "outputs": ["followed"]},
    ]
    guidance, provenance = v622.retrieve(_state(("mixed", schema)), QUERY, registry)
    assert guidance and "apis.venmo.create_transaction" not in guidance
    assert provenance["candidate_scores"][0]["semantic_projection"]["dataflow_edges"] == []


def test_v622_abstains_when_required_public_input_lacks_task_or_dataflow_support():
    _, schema = _schema(required=["apis.music.search_artist", "apis.music.follow_artist"])
    schema["typed_constraints"] = [
        {"operation": "apis.music.search_artist", "required": ["bank_account_id"], "outputs": ["artist_id"]},
        {"operation": "apis.music.follow_artist", "required": ["artist_id"], "outputs": ["followed"]},
    ]
    guidance, provenance = v622.retrieve(_state(("unsupported", schema)), QUERY, REGISTRY)
    assert guidance == "" and provenance["selected_schema_id"] is None
    assert "prerequisite_input_not_supported_by_public_query_or_dataflow" in provenance["candidate_scores"][0]["rejection_reasons"]


def test_v622_noun_match_does_not_prove_input_for_unqueried_prerequisite():
    _, schema = _schema(required=["apis.music.search_artist", "apis.music.follow_artist"])
    schema["typed_constraints"] = [
        {"operation": "apis.music.search_artist", "required": ["artist_id"], "outputs": ["artist_id"]},
        {"operation": "apis.music.follow_artist", "required": ["artist_id"], "outputs": ["followed"]},
    ]
    guidance, provenance = v622.retrieve(_state(("unproven", schema)), QUERY, REGISTRY)
    assert guidance == "" and provenance["selected_schema_id"] is None
    assert provenance["candidate_scores"][0]["unsupported_public_inputs"] == [
        {"operation": "apis.music.search_artist", "input": "artist_id"}]


def test_v622_preserves_read_write_read_semantic_order():
    _, schema = _schema(required=["apis.music.search_artist", "apis.music.follow_artist", "apis.music.search_artist"])
    schema["terminal_effect"] = "apis.music.search_artist"
    schema["terminal_occurrence_id"] = "apis.music.search_artist#2"
    schema["typed_constraints"] = [
        {"operation": "apis.music.search_artist", "occurrence_index": 1, "required": [], "outputs": ["artist_id"]},
        {"operation": "apis.music.follow_artist", "occurrence_index": 2, "required": ["artist_id"], "outputs": ["followed"]},
        {"operation": "apis.music.search_artist", "occurrence_index": 3, "required": ["followed"], "outputs": ["artist_id"]},
    ]
    schema["attested_dataflow_edges"] = [
        {"from_occurrence_id": "apis.music.search_artist#1", "to_occurrence_id": "apis.music.follow_artist#1",
         "producer_slot": "artist_id", "consumer_slot": "artist_id",
         "attestation": "redacted_value_equality_in_every_success"},
        {"from_occurrence_id": "apis.music.follow_artist#1", "to_occurrence_id": "apis.music.search_artist#2",
         "producer_slot": "followed", "consumer_slot": "followed",
         "attestation": "redacted_value_equality_in_every_success"},
    ]
    query = {**QUERY, "canonical_query_operations": ["apis.music.search_artist"]}
    guidance, provenance = v622.retrieve(_state(("loop", schema)), query, REGISTRY)
    assert guidance and provenance["selected_schema_id"] == "loop"
    assert (guidance.index("[apis.music.search_artist#1]") < guidance.index("[apis.music.follow_artist#1]")
            < guidance.index("[apis.music.search_artist#2]"))
    tampered = copy.deepcopy(provenance)
    tampered["candidate_scores"][0]["semantic_projection"]["occurrences"].reverse()
    with pytest.raises(ValueError, match="retrieval provenance mismatch"):
        v622.reproduce_retrieval(_state(("loop", schema)), query, REGISTRY, tampered)


def test_learned_read_write_read_keeps_post_write_read_in_executor_guidance():
    operations = ["apis.music.search_artist", "apis.music.follow_artist", "apis.music.search_artist"]
    nodes = tuple({"operation": operation, "effect_class": "write" if position == 1 else "read",
                   "public_required": requirements, "output_slots": outputs,
                   "index": position}
                  for position, (operation, requirements, outputs) in enumerate(zip(
                      operations, [[], ["artist_id"], ["followed"]],
                      [["artist_id"], ["followed"], ["artist_snapshot"]])))
    edges = ({"kind": "redacted_dataflow", "from": 0, "to": 1,
              "producer_slot": "artist_id", "consumer_slot": "artist_id"},
             {"kind": "redacted_dataflow", "from": 1, "to": 2,
              "producer_slot": "followed", "consumer_slot": "followed"})
    graph = Graph("public-registry", nodes, edges, digest({"nodes": nodes, "edges": edges}))
    audit = {"semantic_projection_sha256": "projected", "provenance_sha256": "attested"}
    plan = semantic_spine_plan([graph, graph], [], {}, [audit, audit])
    assert plan["schema"]["required_operations"] == operations
    assert plan["schema"]["terminal_effect"] == "apis.music.follow_artist"
    validation = validate_semantic_spine(plan, REGISTRY)
    state, completion = commit_semantic_spine({}, plan, validation)
    assert completion["state"] == "committed"
    guidance, provenance = v622.retrieve(state, QUERY, REGISTRY)
    assert guidance and provenance["selected_schema_id"]
    assert (guidance.index("[apis.music.search_artist#1]") < guidance.index("[apis.music.follow_artist#1]")
            < guidance.index("[apis.music.search_artist#2]"))
    assert v622.reproduce_retrieval(state, QUERY, REGISTRY, provenance) == guidance


def test_v622_rejects_misaligned_positional_constraint():
    _, schema = _schema(required=["apis.music.search_artist", "apis.music.follow_artist"])
    schema["typed_constraints"][1]["occurrence_index"] = 1
    guidance, provenance = v622.retrieve(_state(("bad", schema)), QUERY, REGISTRY)
    assert guidance == "" and provenance["selected_schema_id"] is None
    assert any("semantic_projection_invalid" in reason for reason in provenance["candidate_scores"][0]["rejection_reasons"])


def test_v622_rejects_extra_and_implicitly_reused_typed_constraints():
    _, extra = _schema(required=["apis.music.follow_artist"])
    extra["typed_constraints"].append({"operation": "apis.music.search_artist", "required": [], "outputs": []})
    guidance, provenance = v622.retrieve(_state(("extra", extra)), QUERY, REGISTRY)
    assert guidance == ""
    assert "non-required" in provenance["candidate_scores"][0]["rejection_reasons"][0]
    _, reused = _schema(required=["apis.music.search_artist", "apis.music.search_artist",
                                  "apis.music.follow_artist"])
    reused["typed_constraints"] = [
        {"operation": "apis.music.search_artist", "required": [], "outputs": ["artist_id"]},
        {"operation": "apis.music.follow_artist", "required": ["artist_id"], "outputs": ["followed"]},
    ]
    guidance, provenance = v622.retrieve(_state(("reused", reused)), QUERY, REGISTRY)
    assert guidance == ""
    assert "cover occurrences exactly" in provenance["candidate_scores"][0]["rejection_reasons"][0]


def test_legacy_repeated_terminal_without_explicit_group_abstains():
    _, schema = _schema(required=["apis.music.follow_artist", "apis.music.follow_artist"])
    schema.pop("terminal_occurrence_id", None)
    schema.pop("attested_dataflow_edges", None)
    guidance, provenance = v622.retrieve(_state(("ambiguous", schema)), QUERY, REGISTRY)
    assert guidance == ""
    assert "terminal occurrence is ambiguous" in provenance["candidate_scores"][0]["rejection_reasons"][0]


def test_v622_empty_and_duplicate_dependency_closure_is_deterministic():
    _id, schema = _schema(required=["apis.music.follow_artist"])
    schema["typed_constraints"] = [{"operation": "apis.music.follow_artist", "required": [], "outputs": ["followed"]}]
    first, one = v622.retrieve(_state(("one", copy.deepcopy(schema))), QUERY, REGISTRY)
    second, two = v622.retrieve(_state(("one", copy.deepcopy(schema))), QUERY, REGISTRY)
    assert first == second and one == two


def test_attested_terminal_loop_is_parameterized_without_losing_occurrences():
    nodes = ({"operation": "apis.music.search_artist", "effect_class": "read", "public_required": [],
              "output_slots": ["artist_id"], "index": 0},) + tuple(
        {"operation": "apis.music.follow_artist", "effect_class": "write", "public_required": ["artist_id"],
         "output_slots": ["followed"], "index": index} for index in range(1, 20))
    edges = tuple({"kind": "redacted_dataflow", "from": 0, "to": index,
                   "producer_slot": "artist_id", "consumer_slot": "artist_id"}
                  for index in range(1, 20))
    graph = Graph("public-registry", nodes, edges, digest({"nodes": nodes, "edges": edges}))
    audit = {"semantic_projection_sha256": "projected", "provenance_sha256": "attested"}
    plan = semantic_spine_plan([graph, graph], [], {}, [audit, audit])
    validation = validate_semantic_spine(plan, REGISTRY)
    assert validation["passed"] is True
    assert len(plan["schema"]["terminal_occurrence_ids"]) == 19
    state, marker = commit_semantic_spine({}, plan, validation)
    assert marker["state"] == "committed"
    guidance, provenance = v622.retrieve(state, QUERY, REGISTRY)
    assert guidance.count("apis.music.follow_artist") == 2
    assert "19 attested occurrences" in guidance
    projection = provenance["candidate_scores"][0]["semantic_projection"]
    assert len(projection["terminal_occurrence_ids"]) == 19
    assert len(projection["occurrences"]) == 20
