from __future__ import annotations

import pytest

from scripts import run_v625_safe_terminal_slice_100x3 as overlay


def test_overlay_accepts_only_a_complete_distinct_four_arm_grid() -> None:
    task_ids = [f"abc{i:04d}_1" for i in range(overlay.TASK_COUNT)]
    assert overlay._selection(task_ids) == task_ids


@pytest.mark.parametrize("task_ids", [
    [f"abc{i:04d}_1" for i in range(overlay.TASK_COUNT - 1)],
    ["same_1"] * overlay.TASK_COUNT,
])
def test_overlay_rejects_a_changed_or_incomplete_grid(task_ids: list[str]) -> None:
    with pytest.raises(RuntimeError, match="exactly 100 distinct"):
        overlay._selection(task_ids)
