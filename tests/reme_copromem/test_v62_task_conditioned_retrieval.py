from __future__ import annotations

import copy

import pytest

from copromem.contrastive_graph_v6 import digest, retrieve, reproduce_retrieval
from copromem.experiments.reme_copromem.contrastive_v6_runner import retrieval_record
from copromem.experiments.reme_copromem.task_query import derive_task_query, validate_task_query


REGISTRY = {"registry_sha256": "registry-v62", "operations": [
    {"operation": "apis.spotify.follow_artist", "app": "spotify", "access_mode": "write"},
    {"operation": "apis.venmo.request_money", "app": "venmo", "access_mode": "write"},
]}
META_SPOTIFY = {"app_descriptions": {"spotify": "public Spotify tools"}}
META_VENMO = {"app_descriptions": {"venmo": "public Venmo tools"}}


def _state() -> dict:
    return {"contrastive_v6_schemas": {
        "spotify": {"registry_sha256": "registry-v62", "required_operations": ["apis.spotify.follow_artist"], "terminal_effect": "apis.spotify.follow_artist"},
        "venmo": {"registry_sha256": "registry-v62", "required_operations": ["apis.venmo.request_money"], "terminal_effect": "apis.venmo.request_money"},
    }}


def test_public_instructions_produce_bank_independent_cross_domain_queries():
    spotify = derive_task_query("Follow artist using Spotify", "appworld", META_SPOTIFY, REGISTRY)
    venmo = derive_task_query("Request money using Venmo", "appworld", META_VENMO, REGISTRY)
    assert spotify["query_sha256"] != venmo["query_sha256"]
    assert spotify["query_operations"] == ["apis.spotify.follow_artist"]
    assert venmo["query_operations"] == ["apis.venmo.request_money"]
    # Query construction never receives, reads, or depends on the bank.
    assert derive_task_query("Follow artist using Spotify", "appworld", META_SPOTIFY, REGISTRY) == spotify


def test_incompatible_cross_app_schema_is_not_selected_and_empty_is_valid():
    query = derive_task_query("Follow artist using Spotify", "appworld", META_SPOTIFY, REGISTRY)
    guidance, provenance = retrieval_record(state={"contrastive_v6_schemas": {"venmo": _state()["contrastive_v6_schemas"]["venmo"]}},
                                             query_operations=query["query_operations"], registry_sha256="registry-v62", task_query=query)
    assert guidance == "" and provenance["selected_schema_id"] is None
    validate_task_query(query, instruction="Follow artist using Spotify", public_tool_metadata=META_SPOTIFY, callable_registry=REGISTRY)


def test_fixed_dynamic_state_ownership_has_no_alias_or_cross_mutation():
    fixed = _state(); dynamic = copy.deepcopy(fixed)
    assert digest(fixed) == digest(dynamic) and fixed is not dynamic
    before = digest(fixed)
    dynamic["contrastive_v6_schemas"]["dynamic-only"] = copy.deepcopy(dynamic["contrastive_v6_schemas"]["spotify"])
    assert digest(fixed) == before and "dynamic-only" not in fixed["contrastive_v6_schemas"]


def test_empty_or_tampered_query_fails_closed_or_reproduces_exactly():
    empty = derive_task_query("Please help", "appworld", META_SPOTIFY, REGISTRY)
    assert empty["query_operations"] == [] and empty["derivation_status"] == "empty_public_query"
    query = derive_task_query("Follow artist using Spotify", "appworld", META_SPOTIFY, REGISTRY)
    guidance, provenance = retrieve(_state(), query["query_operations"], "registry-v62")
    assert guidance == reproduce_retrieval(_state(), query["query_operations"], provenance)
    tampered = dict(query); tampered["query_operations"] = []
    with pytest.raises(ValueError):
        validate_task_query(tampered, instruction="Follow artist using Spotify", public_tool_metadata=META_SPOTIFY, callable_registry=REGISTRY)
