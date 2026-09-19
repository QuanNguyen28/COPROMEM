"""Tests for the official WebArena dataset loader and multi-scale sampler."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from copromem.types import JoinIntent, JoinTask
from copromem.webarena_loader import (
    DOMAIN_KEYS,
    download_webarena_official,
    filter_webarena_official_domains,
    load_webarena_official_tasks,
)


def test_download_and_cache_webarena(tmp_path: Path) -> None:
    cache_file = tmp_path / "mock_test.raw.json"
    mock_data = [
        {"task_id": 1, "sites": ["shopping"], "intent": "Find running shoes", "start_url": "http://shop.com"},
        {"task_id": 2, "sites": ["gitlab"], "intent": "Create a branch", "start_url": "http://git.com"},
    ]
    with cache_file.open("w", encoding="utf-8") as f:
        json.dump(mock_data, f)

    tasks = download_webarena_official(cache_path=cache_file)
    assert len(tasks) == 2
    assert tasks[0]["task_id"] == 1


def test_filter_webarena_domains() -> None:
    mock_data = [
        {"task_id": 1, "sites": ["shopping"], "intent": "Buy shoes"},
        {"task_id": 2, "sites": ["shopping_admin"], "intent": "Update stock"},
        {"task_id": 3, "sites": ["gitlab"], "intent": "Merge PR"},
        {"task_id": 4, "sites": ["reddit"], "intent": "Comment on post"},
        {"task_id": 5, "sites": ["gitlab", "reddit"], "intent": "Sync accounts"},
        {"task_id": 6, "sites": ["map"], "intent": "Find directions"},  # Excluded pure map
        {"task_id": 7, "sites": ["map", "wikipedia"], "intent": "Find park"},  # Excluded map multi
    ]
    domains = filter_webarena_official_domains(mock_data)
    assert len(domains["web_shopping"]) == 1
    assert len(domains["web_shopping_admin"]) == 1
    assert len(domains["web_gitlab"]) == 1
    assert len(domains["web_reddit"]) == 1
    assert len(domains["web_multi_domain"]) == 1


def test_load_webarena_official_scales() -> None:
    # 1. Smoke scale: 2 tasks (1 shopping, 1 gitlab)
    tasks_smoke = load_webarena_official_tasks(scale="smoke")
    assert len(tasks_smoke) == 2
    assert tasks_smoke[0].group_id == "web_shopping"
    assert tasks_smoke[1].group_id == "web_gitlab"
    assert tasks_smoke[0].instruction != ""

    # 2. Diagnostic scale: 20 tasks (4 per domain across 5 domains)
    tasks_diag = load_webarena_official_tasks(scale="diagnostic")
    assert len(tasks_diag) == 20
    domains = {t.group_id for t in tasks_diag}
    assert len(domains) == 5

    # 3. Slice_100 scale: 100 tasks (20 per domain across 5 domains)
    tasks_100 = load_webarena_official_tasks(scale="slice_100")
    assert len(tasks_100) == 100
    for d in DOMAIN_KEYS:
        d_tasks = [t for t in tasks_100 if t.group_id == d]
        assert len(d_tasks) == 20

    # 4. Full scale: all 684 official tasks
    tasks_full = load_webarena_official_tasks(scale="full")
    assert len(tasks_full) == 684

    # 5. Clipping with max_tasks
    tasks_clipped = load_webarena_official_tasks(scale="full", max_tasks=15)
    assert len(tasks_clipped) == 15
