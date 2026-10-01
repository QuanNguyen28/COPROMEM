from __future__ import annotations

import json
from pathlib import Path

import pytest

from copromem.contrastive_graph_v6 import digest
from copromem.experiments.reme_copromem.retrieval_binding_v622 import create, validate


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _fixture(tmp_path: Path):
    guidance = "safe guidance"
    query = {"query_sha256": "q"}
    provenance = {"retrieval_sha256": "r"}
    runtime_semantic = "a" * 64
    runtime, binding = tmp_path / "runtime-identity.json", tmp_path / "retrieval.binding.json"
    _write(runtime, {"runtime_identity_sha256": runtime_semantic})
    runtime_record = __import__("hashlib").sha256(runtime.read_bytes()).hexdigest()
    artifact = {"trajectory_id": "t", "task_id": "task", "arm": "copromem", "trial_id": 1, "seed": 7,
                "history_sha256": "h", "copromem_callback_guidance_sha256": digest(guidance),
                "copromem_callback_guidance_nonempty": True, "injected_memory_sha256": digest(guidance),
                "initial_prompt_messages_sha256": "p", "model_visible_prompt_sha256": "p",
                "model_visible_memory_binding_sha256": "b",
                "runtime_identity_record_sha256": runtime_record,
                "runtime_identity_semantic_sha256": runtime_semantic}
    retrieval = {"guidance": guidance, "task_query": query, "provenance": provenance}
    artifact_path, retrieval_path = tmp_path / "artifact.json", tmp_path / "retrieval.json"
    _write(artifact_path, artifact); _write(retrieval_path, retrieval)
    return artifact_path, retrieval_path, runtime, binding, retrieval


def test_binding_is_atomic_idempotent_and_reproduced_before_restart(tmp_path):
    artifact, retrieval, runtime, binding, record = _fixture(tmp_path)
    first = create(artifact_path=artifact, retrieval_path=retrieval, binding_path=binding,
                   runtime_identity_record_path=runtime)
    assert create(artifact_path=artifact, retrieval_path=retrieval, binding_path=binding,
                  runtime_identity_record_path=runtime) == first
    observed = validate(artifact_path=artifact, retrieval_path=retrieval, binding_path=binding,
                        runtime_identity_record_path=runtime, state={}, registry={},
                        reproduce=lambda state, query, registry, provenance: record["guidance"])
    assert observed == first


@pytest.mark.parametrize("target", ["artifact", "retrieval", "runtime", "binding"])
def test_binding_rejects_every_immutable_input_change(tmp_path, target):
    artifact, retrieval, runtime, binding, record = _fixture(tmp_path)
    create(artifact_path=artifact, retrieval_path=retrieval, binding_path=binding,
           runtime_identity_record_path=runtime)
    path = {"artifact": artifact, "retrieval": retrieval, "runtime": runtime, "binding": binding}[target]
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises((ValueError, json.JSONDecodeError)):
        validate(artifact_path=artifact, retrieval_path=retrieval, binding_path=binding,
                 runtime_identity_record_path=runtime, state={}, registry={},
                 reproduce=lambda state, query, registry, provenance: record["guidance"])
