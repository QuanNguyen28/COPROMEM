"""Tests for RecursiveTaskDecomposer in COPROMEM."""

from __future__ import annotations

import pytest
from src.copromem.decomposition import (
    RecursiveTaskDecomposer,
    SubGoal,
    HierarchicalExecutionPlan,
)
from src.copromem.copromem_memory_module import ProceduralMemoryItem


def test_is_atomic_classification():
    decomposer = RecursiveTaskDecomposer(api_key="")

    # Atomic tasks
    assert decomposer.is_atomic("Tell me the grand total of invoice 000000001") is True
    assert decomposer.is_atomic("Find customer name and email with phone 8015551212") is True
    assert decomposer.is_atomic("List the top 1 search terms in my store") is True
    assert decomposer.is_atomic("Show me customers dissatisfied with Chloe tank") is True

    # Compound tasks
    assert decomposer.is_atomic("Which customer has completed the most number of orders in history?") is False
    assert decomposer.is_atomic("Which customer has completed the 2nd most orders in history?") is False
    assert decomposer.is_atomic("Monthly count of successful orders from May to December 2022 in MM:COUNT format") is False
    assert decomposer.is_atomic("Total payment of the last 5 completed orders") is False
    assert decomposer.is_atomic("Total payment of the last 5 PENDING orders") is False


def test_atomic_task_plan():
    decomposer = RecursiveTaskDecomposer(api_key="")
    plan = decomposer.decompose("Tell me the grand total of invoice 000000001")

    assert plan.plan_type == "direct_atomic"
    assert len(plan.subgoals) == 1
    assert plan.subgoals[0].is_atomic is True
    assert plan.injected_prompt_text == ""


def test_warm_memory_two_step_macro_plan():
    decomposer = RecursiveTaskDecomposer(api_key="")

    # Suppose Task 62 has been executed and stored in memory
    mem_62 = ProceduralMemoryItem(
        memory_id="mem_task_62",
        intent="Which customer has completed the most number of orders in history?",
        title="Structural subtask workflow for Task 62",
        description="Customer order frequency tallying and ranking",
        procedure="1. Locate Sales -> Orders menu. 2. Scan all order records. 3. Tally counts per customer. 4. Identify 1st highest rank.",
        constraints={"target_type": "customer", "rank": "1st", "aggregation": "frequency"},
        domain="web_shopping_admin",
        success=True,
    )

    # Now Task 63 arrives: "Which customer has completed the 2nd most orders in history?"
    plan = decomposer.decompose(
        intent="Which customer has completed the 2nd most orders in history?",
        memories=[mem_62],
        include_contract_guidance=True,
    )

    assert plan.plan_type == "macro_two_step"
    assert len(plan.subgoals) == 2
    # Step 1: Learned Macro Routine
    assert plan.subgoals[0].bound_memory_id == "mem_task_62"
    assert "Learned Macro-Routine" in plan.subgoals[0].description
    # Step 2: Target Delta
    assert "2nd" in plan.subgoals[1].description or "rank" in plan.subgoals[1].description
    # Invariant checks
    assert any("observation" in inv for inv in plan.checkpoint_invariants)
    assert "# Memory Item: [Observed Successful Routine]" in plan.injected_prompt_text
    assert "Target Adaptation" in plan.injected_prompt_text
    assert "[COMPLETE CONSTRAINT VERIFICATION]" in plan.injected_prompt_text


def test_cold_memory_recursive_fallback():
    # Cold start: empty memories
    decomposer = RecursiveTaskDecomposer(api_key="")
    intent = "Monthly count of successful orders from May to December 2022 in MM:COUNT format"

    plan = decomposer.decompose(intent=intent, memories=[], include_contract_guidance=True)

    assert plan.plan_type == "recursive_atomic"
    assert len(plan.subgoals) >= 2
    # Invariants for verification
    assert any("observation" in inv for inv in plan.checkpoint_invariants)
    assert "[COMPLETE CONSTRAINT VERIFICATION]" in plan.injected_prompt_text
    assert "Milestone" in plan.injected_prompt_text
