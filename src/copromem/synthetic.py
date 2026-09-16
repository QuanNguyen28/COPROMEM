"""Reproducible synthetic join tasks for a small end-to-end CoProMem pilot."""

from __future__ import annotations

from .types import JoinIntent, JoinTask


def make_join_tasks(
    split: str, groups: int, include_boundaries: bool = False
) -> list[JoinTask]:
    """Create grouped templates, keeping variants of a template together.

    Each group includes a safe one-to-one success and two non-trivial
    row-preserving joins.  This gives extraction a success/failure pair without
    leaking descendants across splits. Optional expansion tasks are deliberately
    similar lexical neighbours but lie outside the contract scope.
    """

    tasks: list[JoinTask] = []
    for index in range(groups):
        group_id = f"{split}-template-{index:02d}"
        left_rows = 20 + index * 3
        rows = (
            ("one-to-one", left_rows, JoinIntent.PRESERVE_ROWS),
            ("one-to-many", left_rows * 2, JoinIntent.PRESERVE_ROWS),
            ("many-to-one", left_rows, JoinIntent.PRESERVE_ROWS),
        )
        for kind, expected, intent in rows:
            tasks.append(
                JoinTask(
                    task_id=f"{group_id}-{kind}",
                    group_id=group_id,
                    left_rows=left_rows,
                    actual_cardinality=kind,
                    expected_rows=expected,
                    intent=intent,
                )
            )
        if include_boundaries:
            tasks.append(
                JoinTask(
                    task_id=f"{group_id}-intentional-expansion",
                    group_id=group_id,
                    left_rows=left_rows,
                    actual_cardinality="many-to-many",
                    expected_rows=left_rows * 3,
                    intent=JoinIntent.INTENTIONAL_EXPANSION,
                )
            )
    return tasks


def grouped_split() -> dict[str, list[JoinTask]]:
    """Small fixed build/dev/audit/final split with no template leakage."""

    return {
        "build": make_join_tasks("build", groups=10),
        "dev": make_join_tasks("dev", groups=5),
        "audit": make_join_tasks("audit", groups=3, include_boundaries=True),
        "final": make_join_tasks("final", groups=8, include_boundaries=True),
    }
