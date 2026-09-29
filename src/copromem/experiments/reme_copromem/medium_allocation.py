"""Public-only deterministic allocation for the v6.2 medium held-out study.

The module deliberately accepts only IDs and public family metadata.  It does
not import AppWorld, instantiate a task, or inspect an instruction/payload.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any, Iterable, Mapping


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def family_of(task_id: str) -> str:
    """Return the public AppWorld task family component without opening a task."""
    prefix, marker, suffix = str(task_id).rpartition("_")
    if not prefix or marker != "_" or not suffix.isdecimal():
        raise ValueError("public inventory contains a malformed task ID")
    return prefix


def allocate_round_robin(*, inventory_ids: Iterable[str], hard_exposed_ids: Iterable[str],
                         ambiguous_ids: Iterable[str], count: int = 30) -> Mapping[str, Any]:
    """Select distinct public IDs by deterministic, family-round-robin order.

    Round one contributes the first eligible ID from each sorted family; later
    rounds contribute the second, third, and so on.  This avoids silently
    concentrating an exploratory allocation in one family while retaining a
    fully reproducible rule.
    """
    if count <= 0:
        raise ValueError("allocation count must be positive")
    inventory = sorted(set(str(item) for item in inventory_ids))
    hard, ambiguous = set(map(str, hard_exposed_ids)), set(map(str, ambiguous_ids))
    excluded = hard | ambiguous
    groups: dict[str, list[str]] = defaultdict(list)
    for task_id in inventory:
        if task_id not in excluded:
            groups[family_of(task_id)].append(task_id)
    for values in groups.values():
        values.sort()
    candidates = [{"family_id": family, "task_ids": groups[family]}
                  for family in sorted(groups)]
    selected: list[str] = []
    round_index = 0
    while len(selected) < count:
        added = False
        for family in sorted(groups):
            values = groups[family]
            if round_index < len(values):
                selected.append(values[round_index]); added = True
                if len(selected) == count:
                    break
        if not added:
            break
        round_index += 1
    selected_families = [family_of(task_id) for task_id in selected]
    return {
        "version": "v6.2-medium-public-round-robin-v1",
        "split": "test_normal",
        "payloads_opened": False,
        "ordering_rule": "family_id ascending; then task_id ascending; round-robin by family occurrence",
        "inventory_count": len(inventory),
        "inventory_sha256": canonical_digest(inventory),
        "hard_exclusion_count": len(hard),
        "hard_exclusion_sha256": canonical_digest(sorted(hard)),
        "ambiguous_exclusion_count": len(ambiguous),
        "ambiguous_exclusion_sha256": canonical_digest(sorted(ambiguous)),
        "eligible_family_count": len(groups),
        "candidate_family_groups": candidates,
        "candidate_list_sha256": canonical_digest(candidates),
        "selected_task_ids": selected,
        "selected_family_ids": selected_families,
        "selected_task_ids_sha256": canonical_digest(selected),
        "selected_family_ids_sha256": canonical_digest(selected_families),
        "requested_count": count,
        "selected_count": len(selected),
        "remaining_eligible_count": sum(len(values) for values in groups.values()) - len(selected),
        "sufficient": len(selected) == count,
    }

