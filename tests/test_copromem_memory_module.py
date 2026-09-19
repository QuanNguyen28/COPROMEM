"""Unit tests for COPROMEMMemoryModule."""

from copromem.copromem_memory_module import COPROMEMMemoryModule


def test_copromem_memory_module_arms():
    module = COPROMEMMemoryModule()

    # 1. no_memory arm returns empty
    res_no = module.retrieve_memory("no_memory", "task_01", "Find product", "web_shopping", ["shopping"])
    assert res_no.injected_text == ""
    assert res_no.arm == "no_memory"

    # 2. reasoningbank arm returns # Memory Item format
    res_rb = module.retrieve_memory("reasoningbank", "task_01", "Find product", "web_shopping", ["shopping"])
    assert "# Memory Item" in res_rb.injected_text
    assert "## Title" in res_rb.injected_text
    assert "## Content" in res_rb.injected_text
    assert res_rb.arm == "reasoningbank"

    # 3. semantic_rag arm returns Naive RAG format without pattern separation
    res_sr = module.retrieve_memory("semantic_rag", "task_01", "Find product", "web_shopping", ["shopping"])
    assert "[Naive RAG" in res_sr.injected_text
    assert res_sr.arm == "semantic_rag"
    assert res_sr.separated is False
    assert res_sr.should_veto is False

    # 4. copromem_v2 arm returns Verified Contract
    res_cp = module.retrieve_memory("copromem_v2", "task_01", "Find product", "web_shopping", ["shopping"])
    assert "[COPROMEM 2.0" in res_cp.injected_text
    assert res_cp.arm == "copromem_v2"
    assert res_cp.schema is not None


def test_copromem_memory_module_pattern_separation():
    module = COPROMEMMemoryModule()
    # Task with divergence/veto condition
    res = module.retrieve_memory(
        "copromem_v2",
        "task_veto",
        "Cancel and abort order diverge freeze",
        "web_shopping",
        ["shopping"],
    )
    assert res.arm == "copromem_v2"
