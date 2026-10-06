from __future__ import annotations

from copromem.experiments.reme_copromem import task_conditioned_retrieval_v623 as v623


def _registry(*operations: str) -> dict:
    return {"registry_sha256": "registry", "normalization": {"operation_aliases": {}},
            "operations": [{"operation": item, "http_method": "POST"} for item in operations],
            "dependency_edges": []}


def _schema(terminal: str) -> dict:
    return {"policy_version": "copromem-v6.1-semantic-graph-v1", "registry_sha256": "registry",
            "required_operations": [terminal], "terminal_effect": terminal,
            "typed_constraints": [{"operation": terminal, "occurrence_index": 1, "required": [], "outputs": ["result"]}],
            "support": {"successes": 2, "failures": 0, "failure_counts": {}}}


def _metadata() -> dict:
    return {"app_descriptions": {"music": "public music application", "venmo": "public payments"}}


def test_v623_admits_only_unique_named_app_complete_noun_terminal() -> None:
    registry = _registry("apis.music.follow_artist")
    instruction = "In the music app, handle this artist."
    query = v623.derive_task_query(instruction, "appworld", _metadata(), registry)
    assert query["canonical_query_operations"] == ["apis.music.follow_artist"]
    assert query["terminal_relaxation"]["added_operations"] == ["apis.music.follow_artist"]
    v623.validate_task_query(query, instruction=instruction, public_tool_metadata=_metadata(), callable_registry=registry)
    guidance, provenance = v623.retrieve({"contrastive_v6_schemas": {"one": _schema("apis.music.follow_artist")}}, query, registry)
    assert guidance and provenance["selected_schema_id"] == "one"


def test_v623_abstains_for_ambiguous_same_app_noun() -> None:
    registry = _registry("apis.music.follow_artist", "apis.music.unfollow_artist")
    instruction = "In the music app, handle this artist."
    query = v623.derive_task_query(instruction, "appworld", _metadata(), registry)
    assert query["canonical_query_operations"] == []
    guidance, provenance = v623.retrieve({"contrastive_v6_schemas": {"one": _schema("apis.music.follow_artist")}}, query, registry)
    assert guidance == "" and provenance["selected_schema_id"] is None


def test_v623_does_not_admit_cross_app_terminal() -> None:
    registry = _registry("apis.music.follow_artist", "apis.venmo.create_transaction")
    instruction = "In the music app, handle this artist."
    query = v623.derive_task_query(instruction, "appworld", _metadata(), registry)
    state = {"contrastive_v6_schemas": {"cross": _schema("apis.venmo.create_transaction")}}
    guidance, provenance = v623.retrieve(state, query, registry)
    assert guidance == "" and "terminal_app_not_publicly_relevant" in provenance["candidate_scores"][0]["rejection_reasons"]


def test_v623_does_not_relax_an_unproven_prerequisite() -> None:
    registry = _registry("apis.music.lookup_artist", "apis.music.follow_artist")
    instruction = "In the music app, handle this artist."
    query = v623.derive_task_query(instruction, "appworld", _metadata(), registry)
    schema = {
        "policy_version": "copromem-v6.1-semantic-graph-v1",
        "registry_sha256": "registry",
        "required_operations": ["apis.music.lookup_artist", "apis.music.follow_artist"],
        "terminal_effect": "apis.music.follow_artist",
        "terminal_occurrence_id": "apis.music.follow_artist#1",
        "typed_constraints": [
            {"operation": "apis.music.lookup_artist", "occurrence_index": 1,
             "required": ["private_token"], "outputs": ["artist"]},
            {"operation": "apis.music.follow_artist", "occurrence_index": 2,
             "required": ["artist"], "outputs": ["result"]},
        ],
        "attested_dataflow_edges": [{
            "from_occurrence_id": "apis.music.lookup_artist#1",
            "to_occurrence_id": "apis.music.follow_artist#1",
            "producer_slot": "artist", "consumer_slot": "artist",
            "attestation": "redacted_value_equality_in_every_success",
        }],
        "support": {"successes": 2, "failures": 0, "failure_counts": {}},
    }
    guidance, provenance = v623.retrieve({"contrastive_v6_schemas": {"unsafe": schema}}, query, registry)
    assert guidance == ""
    assert "prerequisite_input_not_supported_by_public_query_or_dataflow" in provenance["candidate_scores"][0]["rejection_reasons"]
