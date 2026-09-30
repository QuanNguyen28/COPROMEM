from __future__ import annotations

from copromem.experiments.reme_copromem.descriptor_screening_v621 import screen_public_descriptor


REGISTRY = {"registry_sha256": "registry", "normalization": {"operation_aliases": {}},
            "operations": [{"operation": "apis.spotify.update_playlist", "app": "spotify", "access_mode": "write"}],
            "dependency_edges": []}
STATE = {"contrastive_v6_schemas": {"schema": {
    "policy_version": "copromem-v6.1-semantic-graph-v1", "registry_sha256": "registry",
    "required_operations": ["apis.spotify.update_playlist"],
    "terminal_effect": "apis.spotify.update_playlist",
    "typed_constraints": [{"operation": "apis.spotify.update_playlist", "required": [], "outputs": []}],
    "support": {"successes": 2, "failures": 0, "failure_counts": {}},
}}}


def test_screening_is_pure_and_sanitized():
    record = screen_public_descriptor(task_id="abcdef0_1", instruction="Update Spotify playlist", app_descriptions={"spotify": "public"}, tool_metadata={"app_descriptions": {"spotify": "public"}}, registry=REGISTRY, state=STATE)
    assert record["compatibility_class"] == "compatible"
    assert record["compatible_schema_ids"] == ["schema"]
    assert "Update Spotify playlist" not in str(record)
    assert record["provider_calls"] == 0
