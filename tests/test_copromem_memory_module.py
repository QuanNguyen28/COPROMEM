"""Unit tests for COPROMEMMemoryModule."""

from copromem.copromem_memory_module import COPROMEMMemoryModule
from src.copromem.decomposition import RecursiveTaskDecomposer


def test_copromem_memory_module_arms():
    module = COPROMEMMemoryModule()
    module.decomposer = RecursiveTaskDecomposer(api_key="")

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

    # 4. copromem_v2 arm returns Execution Guidance (cold start) or Verified Contract (warm start)
    res_cp = module.retrieve_memory("copromem_v2", "task_01", "Find product", "web_shopping", ["shopping"])
    assert res_cp.arm == "copromem_v2"
    assert res_cp.schema is not None
    assert len(res_cp.injected_text) > 0

    # With warm memory, copromem_v2 returns Verified Procedural Contract
    from copromem.copromem_memory_module import ProceduralMemoryItem
    mem = ProceduralMemoryItem(
        memory_id="mem_find_prod",
        intent="Find product",
        title="Find Product Routine",
        description="Search and find product",
        procedure="Navigate to catalog, enter product name",
        domain="web_shopping",
        success=True,
    )
    module.add_memory(mem)
    res_cp_warm = module.retrieve_memory("copromem_v2", "task_01", "Find product", "web_shopping", ["shopping"])
    assert "[COPROMEM 2.0" in res_cp_warm.injected_text
    assert res_cp_warm.arm == "copromem_v2"


def test_copromem_memory_module_pattern_separation():
    module = COPROMEMMemoryModule()
    module.decomposer = RecursiveTaskDecomposer(api_key="")
    # Task with divergence/veto condition
    res = module.retrieve_memory(
        "copromem_v2",
        "task_veto",
        "Cancel and abort order diverge freeze",
        "web_shopping",
        ["shopping"],
    )
    assert res.arm == "copromem_v2"
