from types import SimpleNamespace

from copromem.experiments.reme_copromem.runner import configure_memory_transport


def test_copromem_empty_guidance_cannot_fall_through_to_reme_http():
    agent = SimpleNamespace(get_memory=lambda _query: {"unexpected": True})
    configure_memory_transport(agent, lambda *_args: "")
    assert agent.get_memory("public task instruction") is None


def test_reme_transport_is_unchanged_without_copromem_callback():
    original = lambda _query: {"metadata": {"memory_list": []}}
    agent = SimpleNamespace(get_memory=original)
    configure_memory_transport(agent, None)
    assert agent.get_memory is original
