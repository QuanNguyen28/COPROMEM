import pytest
from src.copromem.decomposition import RecursiveTaskDecomposer, SubGoal, HierarchicalExecutionPlan
from src.copromem.copromem_memory_module import (
    COPROMEMMemoryModule,
    ProceduralMemoryItem,
)


def test_default_prompt_guidance_keeps_decomposition_without_contract_sections():
    intent = "Get the customer name of the most recent cancelled order"
    plan = RecursiveTaskDecomposer(api_key="").decompose(intent)
    assert plan.plan_type == "recursive_atomic"
    assert "Milestone" in plan.injected_prompt_text
    assert "[COMPLETE CONSTRAINT VERIFICATION]" not in plan.injected_prompt_text
    assert "[NON-PREMATURE TERMINATION INVARIANT]" not in plan.injected_prompt_text

    module = COPROMEMMemoryModule(api_key="")
    assert module.include_contract_guidance is False
    result = module.retrieve_memory("copromem_v2", "default_off", intent, "web_shopping_admin")
    assert "[COMPLETE CONSTRAINT VERIFICATION]" not in result.injected_text


def test_constraint_composition_complexity_assessment():
    """Test that multi-stage constraint pipelines are classified as compound."""
    decomposer = RecursiveTaskDecomposer(api_key="")  # Use syntactic fallback to verify pure logic

    # Multi-stage: Condition Scoping + Extremum/Ordering
    compound_intents = [
        "Get the customer name of the most recent cancelled order",
        "Get the billing name of the oldest complete order",
        "Get the purchase date and order id of the most recent pending order",
        "Tell me the name of the customer who has the most cancellations in the history",
        "Tell me the product SKUs in the most recent cancelled orders of the customer with most cancellations",
        "Presents the monthly count of successful orders from May to December 2022 in MM:COUNT format",
        "Get the total payment amount of the last 5 completed orders",
    ]

    for intent in compound_intents:
        is_comp = decomposer.is_compound(intent)
        assert is_comp is True, f"Intent should be classified as compound: {intent}"

    # Truly atomic single-step lookups
    atomic_intents = [
        "Find the customer name and email with phone number 8015551212",
        "Telll me the grand total of invoice 000000001.",
        "Show all customers",
        "Lookup orders",
    ]

    for intent in atomic_intents:
        is_comp = decomposer.is_compound(intent)
        assert is_comp is False, f"Intent should be classified as atomic: {intent}"


def test_subtask_level_memory_binding():
    """Test that memories are bound at the subtask level with explicit boundaries."""
    decomposer = RecursiveTaskDecomposer(api_key="")

    # Prior memory that only addresses the scoping/filtering phase
    prior_mem = ProceduralMemoryItem(
        memory_id="mem_orders_filter",
        intent="filter orders by status and verify records",
        title="Order Status Filtering Routine",
        description="Filter collection by status condition",
        procedure="1. Access orders collection -> 2. Configure status filter parameter -> 3. Commit filter update",
        constraints={"status": "cancelled"},
        success=True,
    )

    intent = "Get the customer name of the most recent cancelled order"
    plan = decomposer.decompose(intent, memories=[prior_mem], include_contract_guidance=True)

    assert plan.plan_type == "recursive_atomic"
    assert len(plan.subgoals) >= 2

    # Verify Milestone 1 received memory binding
    sg1 = plan.subgoals[0]
    assert sg1.bound_memory_id == "mem_orders_filter"
    assert sg1.bound_memory_title == "Order Status Filtering Routine"

    # Verify prompt text clearly isolates subtask boundary
    prompt = plan.injected_prompt_text
    assert "Supported by Prior Memory: Order Status Filtering Routine" in prompt
    assert "This memory routine applies strictly to achieving Milestone 1" in prompt
    assert "Subsequent milestones require independent execution" in prompt

    # Verify Milestone 2 is marked as Novel and contains Ordered Selection Invariant
    sg2 = plan.subgoals[1]
    assert sg2.bound_memory_id is None
    assert "Novel Subtask - Independent Execution" in prompt
    assert "ORDERED SELECTION INVARIANT" in prompt


def test_non_premature_termination_guard():
    """Test that intermediate milestones forbid premature output emission."""
    decomposer = RecursiveTaskDecomposer(api_key="")
    intent = "Get the customer name of the most recent cancelled order"
    plan = decomposer.decompose(intent, include_contract_guidance=True)

    prompt = plan.injected_prompt_text
    assert "[NON-PREMATURE TERMINATION INVARIANT]" in prompt
    assert "You must NOT emit final output or terminate the task until ALL preceding milestones have been verified" in prompt

    # Ensure intermediate subgoals do NOT instruct terminal submission
    for sg in plan.subgoals[:-1]:
        assert "send_msg_to_user" not in sg.description.lower()
        assert "emit output" not in sg.description.lower()


def test_complete_constraint_verification_guard():
    """Test that opportunistic shortcut without verification is eliminated."""
    decomposer = RecursiveTaskDecomposer(api_key="")
    intent = "Get the customer name of the most recent cancelled order"
    plan = decomposer.decompose(intent, include_contract_guidance=True)

    prompt = plan.injected_prompt_text
    assert "[COMPLETE CONSTRAINT VERIFICATION]" in prompt
    assert "An observation may only be used to satisfy a goal or milestone if ALL specified constraints" in prompt
    # Old unsafe shortcut must be gone
    assert "extract and answer directly without navigating away" not in prompt


def test_copromem_memory_module_low_similarity_hygiene():
    """Test that low similarity queries delegate cleanly to decomposition without fake memory titles."""
    mem_mod = COPROMEMMemoryModule(include_contract_guidance=True)
    mem_mod.decomposer = RecursiveTaskDecomposer(api_key="")

    # Add unrelated memory so memory bank is not empty
    unrelated_mem = ProceduralMemoryItem(
        memory_id="mem_tax_report",
        intent="generate tax report for last year",
        title="Tax Report Generator",
        description="Generate tax report",
        procedure="Navigate to Reports -> Tax and generate",
        constraints={"period": "last year"},
        success=True,
    )
    mem_mod.add_memory(unrelated_mem)

    intent = "Get the customer name of the most recent cancelled order"
    res = mem_mod.retrieve_memory("copromem_v2", "task_test", intent, "web_shopping_admin")

    # Injected text must not claim to be a recalled memory item
    assert "# Memory Item: [COPROMEM 2.0 Exploratory Invariant Contract]" not in res.injected_text
    assert "COPROMEM 2.0 Differentiated Contract" not in res.injected_text
    # Must contain structured hierarchical plan with non-premature termination guard
    assert "[NON-PREMATURE TERMINATION INVARIANT]" in res.injected_text
    assert "[COMPLETE CONSTRAINT VERIFICATION]" in res.injected_text
