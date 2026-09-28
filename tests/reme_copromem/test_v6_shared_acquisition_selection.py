from __future__ import annotations

import importlib.util
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("v6_shared", Path(__file__).parents[2] / "scripts" / "run_v6_shared_acquisition.py")
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MOD)


def _row(family: str, number: int) -> dict:
    return {"task_id": f"{family}_{number}", "instruction": f"Do public operation {number}",
            "app_descriptions": {"demo": "public"}}


def test_selection_uses_execution_custody_not_textual_mentions_and_is_canonical():
    inventory = {"unseen_train_tasks": [item for family in ("000000a", "000000b", "000000c", "000000d", "000000e", "000000f", "000000g")
                                        for item in (_row(family, 1), _row(family, 2))]}
    registry = {"registry_sha256": "registry"}
    custody = {"execution_exclusion": ["000000a_1"], "inventory_or_textual_mentions": ["000000b_1"]}
    allocation, audit = MOD.select_allocation(inventory, custody, registry)
    assert len(allocation) == 12 and {item["family"] for item in allocation} == {"000000b", "000000c", "000000d", "000000e", "000000f", "000000g"}
    assert audit["shortfall"] is None
    assert all(item["task_id"] != "000000a_1" for item in allocation)


def test_selection_fails_closed_when_six_two_sibling_families_do_not_exist():
    inventory = {"unseen_train_tasks": [item for family in ("000000a", "000000b", "000000c", "000000d", "000000e")
                                        for item in (_row(family, 1), _row(family, 2))]}
    allocation, audit = MOD.select_allocation(inventory, {"execution_exclusion": []}, {"registry_sha256": "registry"})
    assert allocation == [] and audit["shortfall"] == {"required_families": 6, "available_families": 5}


def test_git_head_resolves_the_current_linked_worktree():
    assert len(MOD.git_head()) == 40
