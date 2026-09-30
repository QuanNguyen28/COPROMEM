from __future__ import annotations

from copromem.experiments.reme_copromem.runner import (configure_memory_transport,
                                                        _copromem_prompt_memory_text,
                                                        _observe_upstream_retrieval, digest)


def test_passive_reme_retrieval_observer_hashes_without_rewriting_response():
    response = {"answer": "Memory 1: do the public operation", "metadata": {"memory_list": [{"id": "m1", "text": "x"}]}}
    observed = _observe_upstream_retrieval(response)
    assert response == {"answer": "Memory 1: do the public operation", "metadata": {"memory_list": [{"id": "m1", "text": "x"}]}}
    assert observed["retrieved_memory_count"] == 1
    assert observed["retrieved_memory_sha256s"] == [digest({"id": "m1", "text": "x"})]
    assert observed["prompt_memory_sha256"] == digest("Experience 1: do the public operation")
    assert not observed["retrieval_empty"]


def test_passive_reme_observer_distinguishes_empty_retrieval_from_copromem_fields():
    observed = _observe_upstream_retrieval(None)
    assert observed["retrieval_empty"] is True
    assert observed["retrieved_memory_count"] == 0
    assert "copromem_callback_guidance_sha256" not in observed


def test_copromem_prompt_memory_hashes_the_exact_upstream_rendering():
    guidance = "# Retrieved response-attested schema: schema"
    assert _copromem_prompt_memory_text(guidance) == (
        "Experience 1:\n When to use: Retrieved procedural guidance\n Content: " + guidance + "\n"
    )
    assert _copromem_prompt_memory_text("") == ""


def test_copromem_transport_disables_upstream_fallback_for_empty_guidance():
    class Agent:
        def get_memory(self, query):
            return {"answer": "unexpected upstream fallback"}

    agent = Agent()
    configure_memory_transport(agent, lambda *_: "")
    assert agent.get_memory("public instruction") is None
