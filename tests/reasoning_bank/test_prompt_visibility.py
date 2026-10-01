from __future__ import annotations

import pytest

from copromem.experiments.reme_copromem.runner import model_visible_memory_binding


def test_nonempty_reasoningbank_memory_must_be_in_exact_model_messages():
    memory = "Below are some memory items\n\n# Memory Item 1"
    messages = [{"role": "user", "content": "Task\n\n" + memory}]
    bound = model_visible_memory_binding(messages, memory)
    assert bound["injected_memory_visible_in_initial_prompt"] is True
    assert len(bound["model_visible_memory_binding_sha256"]) == 64


def test_nonempty_memory_not_present_in_prompt_fails_closed():
    with pytest.raises(RuntimeError, match="absent"):
        model_visible_memory_binding([{"role": "user", "content": "Task"}], "memory")


def test_empty_guidance_is_a_valid_prompt_identical_boundary():
    bound = model_visible_memory_binding([{"role": "user", "content": "Task"}], "")
    assert bound["injected_memory_visible_in_initial_prompt"] is True
