"""Unit tests verifying Pattern Separation veto defense across all key conflict pairs."""

from __future__ import annotations

import pytest
from src.copromem.copromem_memory_module import (
    COPROMEMMemoryModule,
    ProceduralMemoryItem,
)
from src.copromem.decomposition import RecursiveTaskDecomposer


def test_conflict_pair_0_vs_1_product_vs_brand():
    module = COPROMEMMemoryModule(include_contract_guidance=True)
    # Task 0 induces product memory
    mem_0 = ProceduralMemoryItem(
        memory_id="mem_task_0",
        intent="What is the top-1 best-selling product in 2022",
        title="Structural workflow for Task 0",
        description="Extract top best-selling product",
        procedure="Locate bestsellers, read product name",
        constraints={"target_type": "product", "temporal_scope": "2022", "aggregation": "rank", "cardinality": "1"},
        domain="web_shopping_admin",
        success=True,
    )
    module.add_memory(mem_0)

    # Task 1 arrives with divergent target_type: brand
    res = module.retrieve_memory(
        arm="copromem_v2",
        task_id="1",
        intent="What is the top-1 best-selling brand in Quarter 1 2022",
        domain="web_shopping_admin",
    )

    assert res.separated is True
    assert res.should_veto is True
    assert "target_type" in res.injected_text
    assert "brand" in res.injected_text.lower()
    assert "Complete Constraint Verification Guard" in res.injected_text


def test_conflict_pair_4_vs_5_product_vs_type():
    module = COPROMEMMemoryModule(include_contract_guidance=True)
    mem_4 = ProceduralMemoryItem(
        memory_id="mem_task_4",
        intent="What are the top-3 best-selling product in Jan 2023",
        title="Structural workflow for Task 4",
        description="Extract top 3 product names",
        procedure="Locate bestsellers, read product names",
        constraints={"target_type": "product", "temporal_scope": "jan", "aggregation": "rank", "cardinality": "3"},
        domain="web_shopping_admin",
        success=True,
    )
    module.add_memory(mem_4)

    # Task 5 arrives with target_type: product type
    res = module.retrieve_memory(
        arm="copromem_v2",
        task_id="5",
        intent="What is the top-1 best-selling product type in Jan 2023",
        domain="web_shopping_admin",
    )

    assert res.separated is True
    assert res.should_veto is True
    assert "product type" in res.injected_text.lower()


def test_conflict_pair_78_vs_79_approved_vs_not_approved_zero_count():
    module = COPROMEMMemoryModule(include_contract_guidance=True)
    mem_78 = ProceduralMemoryItem(
        memory_id="mem_task_78",
        intent="What is the total count of Approved reviews amongst all the reviews?",
        title="Structural workflow for Task 78",
        description="Extract approved count",
        procedure="Filter by Approved status, read total count",
        constraints={"target_type": "review", "status": "approved", "aggregation": "count"},
        domain="web_shopping_admin",
        success=True,
    )
    module.add_memory(mem_78)

    # Task 79 arrives with status: not approved
    res = module.retrieve_memory(
        arm="copromem_v2",
        task_id="79",
        intent="What is the total count of Not Approved reviews amongst all the reviews?",
        domain="web_shopping_admin",
    )

    assert res.separated is True
    assert res.should_veto is True
    assert "Not Approved" in res.injected_text
    assert "strictly 0" in res.injected_text


def test_conflict_pair_119_vs_213_like_vs_dislike():
    module = COPROMEMMemoryModule(include_contract_guidance=True)
    mem_119 = ProceduralMemoryItem(
        memory_id="mem_task_119",
        intent="Tell me the reasons why customers like Antonia Racer Tank",
        title="Structural workflow for Task 119",
        description="Extract positive feedback",
        procedure="Inspect customer reviews, extract positive quotes",
        constraints={"target_type": "review", "sentiment": "positive"},
        domain="web_shopping_admin",
        success=True,
    )
    module.add_memory(mem_119)

    # Task 213 arrives with negative sentiment
    res = module.retrieve_memory(
        arm="copromem_v2",
        task_id="213",
        intent="Key aspects customers DON'T like about Antonia Racer Tank",
        domain="web_shopping_admin",
    )

    assert res.separated is True
    assert res.should_veto is True
    assert "sentiment" in res.injected_text.lower()
    assert "negative" in res.injected_text.lower()


def test_task_atomic_vs_compound_queries():
    decomposer = RecursiveTaskDecomposer(api_key="")
    # Single-objective operational queries
    assert decomposer.is_compound("Tell me the grand total of invoice 000000001") is False
    assert decomposer.is_compound("Find the customer name and email with phone number 8015551212") is False
    assert decomposer.is_compound("List the top 1 search terms in my store") is False

    # True cross-record compositions
    assert decomposer.is_compound("Which customer has completed the most number of orders in history?") is True
    assert decomposer.is_compound("Which customer has completed the 2nd most orders in history?") is True
    assert decomposer.is_compound("Monthly count of successful orders from May to December 2022 in MM:COUNT format") is True
