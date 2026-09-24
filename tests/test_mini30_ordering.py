"""Unit tests for the 30-task mini-suite and curriculum ordering."""

from __future__ import annotations

import pytest
from src.copromem.webarena_browsergym_benchmark import (
    TEST_SHOPPING_ADMIN_MINI_30,
    TIER_1_EASY_ATOMIC,
    TIER_2_MEDIUM_FILTER,
    TIER_3_HARD_PARAM,
    TIER_4_VERY_HARD_COMPOSITION,
    TASK_TO_TIER,
    order_tasks,
)


def test_mini_30_composition_and_uniqueness():
    assert len(TEST_SHOPPING_ADMIN_MINI_30) == 30
    assert len(set(TEST_SHOPPING_ADMIN_MINI_30)) == 30

    assert len(TIER_1_EASY_ATOMIC) == 6
    assert len(TIER_2_MEDIUM_FILTER) == 8
    assert len(TIER_3_HARD_PARAM) == 8
    assert len(TIER_4_VERY_HARD_COMPOSITION) == 8


def test_negative_transfer_conflict_pairs_present():
    suite_set = set(TEST_SHOPPING_ADMIN_MINI_30)
    conflict_pairs = [
        (94, 95),    # Invoice 000000001 vs 000000002
        (0, 1),      # Product vs Brand
        (0, 3),      # Top 1 vs Top 2
        (41, 42),    # Top 1 vs Top 2 search terms
        (62, 63),    # 1st vs 2nd Most
        (193, 194),  # Complete vs Canceled
        (198, 200),  # Canceled vs Pending customer
        (202, 203),  # Pending vs Canceled grand total
        (184, 185),  # Customer name vs Order number
        (184, 186),  # Customer name vs Grand total
        (185, 186),  # Order number vs Grand total
    ]
    for a, b in conflict_pairs:
        assert a in suite_set, f"Task {a} missing from mini30 suite"
        assert b in suite_set, f"Task {b} missing from mini30 suite"


def test_order_easy_to_hard():
    ordered = order_tasks(TEST_SHOPPING_ADMIN_MINI_30, order="easy-to-hard")
    assert len(ordered) == 30

    # Verify that all Tier 1 tasks appear before any Tier 2 tasks
    tier1_indices = [ordered.index(t) for t in TIER_1_EASY_ATOMIC]
    tier2_indices = [ordered.index(t) for t in TIER_2_MEDIUM_FILTER]
    tier3_indices = [ordered.index(t) for t in TIER_3_HARD_PARAM]
    tier4_indices = [ordered.index(t) for t in TIER_4_VERY_HARD_COMPOSITION]

    assert max(tier1_indices) < min(tier2_indices)
    assert max(tier2_indices) < min(tier3_indices)
    assert max(tier3_indices) < min(tier4_indices)


def test_order_hard_to_easy():
    ordered = order_tasks(TEST_SHOPPING_ADMIN_MINI_30, order="hard-to-easy")
    assert len(ordered) == 30

    tier1_indices = [ordered.index(t) for t in TIER_1_EASY_ATOMIC]
    tier2_indices = [ordered.index(t) for t in TIER_2_MEDIUM_FILTER]
    tier3_indices = [ordered.index(t) for t in TIER_3_HARD_PARAM]
    tier4_indices = [ordered.index(t) for t in TIER_4_VERY_HARD_COMPOSITION]

    assert max(tier4_indices) < min(tier3_indices)
    assert max(tier3_indices) < min(tier2_indices)
    assert max(tier2_indices) < min(tier1_indices)


def test_order_natural():
    ordered = order_tasks(TEST_SHOPPING_ADMIN_MINI_30, order="natural")
    assert ordered == sorted(TEST_SHOPPING_ADMIN_MINI_30)


def test_order_random():
    ordered_1 = order_tasks(TEST_SHOPPING_ADMIN_MINI_30, order="random", seed=42)
    ordered_2 = order_tasks(TEST_SHOPPING_ADMIN_MINI_30, order="random", seed=42)
    ordered_3 = order_tasks(TEST_SHOPPING_ADMIN_MINI_30, order="random", seed=99)

    assert ordered_1 == ordered_2  # deterministic with same seed
    assert ordered_1 != ordered_3  # varies with different seed
    assert set(ordered_1) == set(TEST_SHOPPING_ADMIN_MINI_30)
