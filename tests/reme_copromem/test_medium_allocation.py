from __future__ import annotations

from copromem.experiments.reme_copromem.medium_allocation import allocate_round_robin, family_of


def test_round_robin_is_public_only_and_deterministic():
    result = allocate_round_robin(
        inventory_ids=["bbbbbbb_2", "aaaaaaa_2", "aaaaaaa_1", "ccccccc_1", "bbbbbbb_1"],
        hard_exposed_ids=["aaaaaaa_1"], ambiguous_ids=[], count=4,
    )
    # First pass over families, then a second member where one remains.
    assert result["selected_task_ids"] == ["aaaaaaa_2", "bbbbbbb_1", "ccccccc_1", "bbbbbbb_2"]
    assert result["payloads_opened"] is False
    assert result["sufficient"] is True


def test_ambiguous_custody_is_fail_closed():
    result = allocate_round_robin(inventory_ids=["aaaaaaa_1", "bbbbbbb_1"],
                                  hard_exposed_ids=[], ambiguous_ids=["bbbbbbb_1"], count=2)
    assert result["selected_task_ids"] == ["aaaaaaa_1"]
    assert result["sufficient"] is False


def test_public_family_parser_rejects_non_task_ids():
    assert family_of("abcdef0_12") == "abcdef0"
    try:
        family_of("not-an-appworld-id")
    except ValueError:
        pass
    else:
        raise AssertionError("malformed ID was accepted")
