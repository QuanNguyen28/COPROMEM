"""Official WebArena dataset loader and stratified sampler.

Loads the upstream `test.raw.json` dataset from:
https://raw.githubusercontent.com/web-arena-x/webarena/main/config_files/test.raw.json

Extracts the standard 684 tasks across 5 core domains:
  - Shopping (187 tasks)
  - Shopping Admin (182 tasks)
  - GitLab (180 tasks)
  - Reddit (106 tasks)
  - Multi-domain without map (29 tasks)

Provides multi-scale sampling:
  - smoke: 2 tasks (1 Shopping, 1 GitLab)
  - diagnostic: 20 tasks (4 per domain across 5 domains)
  - conference / slice_100: 100 tasks (20 per domain across 5 domains)
  - full: all 684 tasks
  - max_tasks: flexible custom limit
"""

from __future__ import annotations

import json
import logging
import urllib.request
from pathlib import Path
from typing import Any

from copromem.types import JoinIntent, JoinTask

logger = logging.getLogger(__name__)

WEBARENA_UPSTREAM_URL = (
    "https://raw.githubusercontent.com/web-arena-x/webarena/main/config_files/test.raw.json"
)
DEFAULT_CACHE_PATH = Path("artifacts/datasets/webarena/test.raw.json")

DOMAIN_KEYS = [
    "web_shopping",
    "web_shopping_admin",
    "web_gitlab",
    "web_reddit",
    "web_multi_domain",
]

DOMAIN_ACTIONS = {
    "web_shopping": ("cart_to_checkout", "cancel_pending_order"),
    "web_shopping_admin": ("inventory_sku_update", "permission_denied_edit"),
    "web_gitlab": ("merge_request_submit", "repo_fork_divergence"),
    "web_reddit": ("post_nested_reply", "thread_locked_veto"),
    "web_multi_domain": ("cross_site_order_sync", "token_auth_revoked"),
}


def download_webarena_official(
    cache_path: Path | str | None = None,
    url: str = WEBARENA_UPSTREAM_URL,
    timeout: int = 30,
) -> list[dict[str, Any]]:
    """Download and cache official WebArena raw tasks."""
    target_path = Path(cache_path or DEFAULT_CACHE_PATH)
    if target_path.is_file():
        try:
            with target_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and len(data) > 0:
                logger.info(f"Loaded {len(data)} WebArena tasks from cache: {target_path}")
                return data
        except Exception as err:
            logger.warning(f"Corrupted cache at {target_path}: {err}. Re-downloading...")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Downloading official WebArena dataset from {url}...")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "COPROMEM-Benchmark-Runner/2.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        content = resp.read().decode("utf-8")

    data = json.loads(content)
    with target_path.open("w", encoding="utf-8") as f:
        f.write(content)
    logger.info(f"Successfully cached {len(data)} tasks to {target_path}")
    return data


def filter_webarena_official_domains(
    raw_tasks: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Filter and partition official raw tasks into the 5 standard benchmark domains (684 tasks total).

    The 684 tasks exclude pure map (109) and map multi-domain (19) tasks to match standard evaluations:
      - web_shopping: 187
      - web_shopping_admin: 182
      - web_gitlab: 180
      - web_reddit: 106
      - web_multi_domain: 29
    """
    domains: dict[str, list[dict[str, Any]]] = {k: [] for k in DOMAIN_KEYS}

    for task in raw_tasks:
        sites = task.get("sites", [])
        if not sites:
            continue
        # Check domain partitioning
        if sites == ["shopping"]:
            domains["web_shopping"].append(task)
        elif sites == ["shopping_admin"]:
            domains["web_shopping_admin"].append(task)
        elif sites == ["gitlab"]:
            domains["web_gitlab"].append(task)
        elif sites == ["reddit"]:
            domains["web_reddit"].append(task)
        elif len(sites) > 1 and "map" not in sites:
            domains["web_multi_domain"].append(task)

    return domains


def _raw_to_jointask(
    raw: dict[str, Any],
    domain: str,
    index: int,
) -> JoinTask:
    """Convert an official WebArena task dictionary to a typed JoinTask with real prompt metadata."""
    tid = raw.get("task_id", index)
    sites = tuple(raw.get("sites", [domain]))
    intent_text = raw.get("intent", "").strip()
    norm_action, twin_action = DOMAIN_ACTIONS.get(domain, ("standard_exec", "veto_action"))

    # Determine if task exhibits counterfactual/divergence characteristics
    is_twin = False
    lower_intent = intent_text.lower()
    veto_keywords = ("cancel", "revert", "delete", "stop", "locked", "reject", "deny", "diverge", "freeze")
    if any(kw in lower_intent for kw in veto_keywords):
        is_twin = True

    cardinality = twin_action if is_twin else norm_action
    expected_rows = 0 if is_twin else (2 + (index % 4))
    join_intent = JoinIntent.INTENTIONAL_EXPANSION if is_twin else JoinIntent.PRESERVE_ROWS

    # Collect join keys from sites and intent tokens
    keys = list(sites)
    if "order" in lower_intent or "cart" in lower_intent:
        keys.append("cart_id")
    if "pr" in lower_intent or "branch" in lower_intent or "merge" in lower_intent:
        keys.append("branch_id")
    if "user" in lower_intent or "account" in lower_intent:
        keys.append("user_id")

    return JoinTask(
        task_id=f"webarena_official_{tid:03d}",
        group_id=domain,
        left_rows=2 + (index % 4),
        actual_cardinality=cardinality,
        expected_rows=expected_rows,
        intent=join_intent,
        join_keys=tuple(keys),
        instruction=intent_text,
        sites=sites,
        start_url=raw.get("start_url", ""),
        require_login=bool(raw.get("require_login", False)),
        eval_spec=raw.get("eval", {}),
    )


def load_webarena_official_tasks(
    scale: str = "conference",
    max_tasks: int | None = None,
    cache_path: Path | str | None = None,
    seed: int = 42,
) -> list[JoinTask]:
    """Load stratified WebArena tasks from official upstream data across flexible scales.

    Supported scales:
      - 'smoke': 2 tasks (1 shopping, 1 gitlab)
      - 'diagnostic': 20 tasks (4 per domain across 5 domains)
      - 'conference' or 'slice_100': 100 tasks (20 per domain across 5 domains)
      - 'full': all 684 official tasks across all 5 domains
    """
    raw_tasks = download_webarena_official(cache_path=cache_path)
    domains = filter_webarena_official_domains(raw_tasks)

    scale_normalized = scale.lower().strip()
    selected_tasks: list[JoinTask] = []

    if scale_normalized == "smoke":
        # 1 task from shopping, 1 from gitlab
        shop_tasks = domains["web_shopping"][:1]
        git_tasks = domains["web_gitlab"][:1]
        for i, t in enumerate(shop_tasks):
            selected_tasks.append(_raw_to_jointask(t, "web_shopping", i))
        for i, t in enumerate(git_tasks):
            selected_tasks.append(_raw_to_jointask(t, "web_gitlab", i))

    elif scale_normalized == "diagnostic":
        # 4 tasks per domain across 5 domains = 20 tasks
        for d in DOMAIN_KEYS:
            for i, t in enumerate(domains[d][:4]):
                selected_tasks.append(_raw_to_jointask(t, d, i))

    elif scale_normalized in ("conference", "slice_100"):
        # 20 tasks per domain across 5 domains = 100 tasks
        for d in DOMAIN_KEYS:
            for i, t in enumerate(domains[d][:20]):
                selected_tasks.append(_raw_to_jointask(t, d, i))

    elif scale_normalized == "full":
        # All 684 official tasks across 5 domains
        for d in DOMAIN_KEYS:
            for i, t in enumerate(domains[d]):
                selected_tasks.append(_raw_to_jointask(t, d, i))

    else:
        # Default fallback: 20 per domain
        for d in DOMAIN_KEYS:
            for i, t in enumerate(domains[d][:20]):
                selected_tasks.append(_raw_to_jointask(t, d, i))

    if max_tasks is not None and max_tasks > 0:
        selected_tasks = selected_tasks[:max_tasks]

    return selected_tasks
