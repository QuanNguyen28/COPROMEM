"""Thin ALFWorld adapter for the pinned upstream ReasoningBank checkout.

The adapter translates ALFWorld episodes into ReasoningBank's WebArena data
shape. Retrieval, trajectory formatting, prompts, client selection, and memory
item generation are delegated to upstream modules rather than reimplemented.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


UPSTREAM_REPO = "https://github.com/google-research/reasoning-bank"
UPSTREAM_COMMIT = "ed80611"
DEFAULT_CHECKOUT = (
    Path(__file__).resolve().parents[2] / "external" / "reasoning-bank"
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def memory_text(item: dict[str, Any] | None) -> str:
    if not item:
        return ""
    return "\n\n".join(
        str(value).strip()
        for value in item.get("memory_items") or []
        if str(value).strip()
    ).strip()


def _response_metadata(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage", None)
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump()
    elif usage is not None and not isinstance(usage, dict):
        usage = {
            key: getattr(usage, key)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens", "cost")
            if getattr(usage, key, None) is not None
        }
    return {
        "response_id": getattr(response, "id", None),
        "model": getattr(response, "model", None),
        "usage": usage or {},
    }


@dataclass(frozen=True)
class Retrieval:
    guidance: str
    selected: dict[str, Any] | None

    def as_dict(self, embedding_model: str) -> dict[str, Any]:
        item = self.selected
        return {
            "top_k": 1,
            "selected_task_id": item.get("task_id") if item else None,
            "selected_global_task_index": item.get("global_task_index") if item else None,
            "memory_items": len(item.get("memory_items") or []) if item else 0,
            "guidance": self.guidance,
            "embedding_model": embedding_model,
            "upstream_commit": UPSTREAM_COMMIT,
            "implementation": "upstream_adapter",
        }


class ReasoningBankALFWorldAdapter:
    """Translate ALFWorld records and invoke official ReasoningBank functions."""

    def __init__(
        self,
        *,
        model: str,
        bank_path: Path,
        embeddings_path: Path,
        checkout: Path = DEFAULT_CHECKOUT,
        max_tokens: int = 1024,
        validate_commit: bool = True,
    ) -> None:
        self.model = model
        self.bank_path = Path(bank_path)
        self.embeddings_path = Path(embeddings_path)
        self.checkout = Path(checkout).resolve()
        self.webarena = self.checkout / "WebArena"
        self.max_tokens = int(max_tokens)
        self.embedding_model = os.environ.get(
            "REASONING_BANK_EMBEDDING_MODEL",
            "openai/text-embedding-3-small",
        )
        self.commit = self._commit() if validate_commit else UPSTREAM_COMMIT
        if validate_commit and not self.commit.startswith(UPSTREAM_COMMIT):
            raise RuntimeError(
                f"ReasoningBank checkout must be pinned to {UPSTREAM_COMMIT}; "
                f"found {self.commit or 'unknown'} at {self.checkout}"
            )
        if not self.webarena.is_dir():
            raise FileNotFoundError(
                f"ReasoningBank WebArena checkout not found: {self.webarena}. "
                "Run COPROMEM/integrations/reasoning_bank/setup.sh first."
            )

        webarena_text = str(self.webarena)
        if webarena_text not in sys.path:
            sys.path.insert(0, webarena_text)
        memory_management = importlib.import_module("memory_management")
        induce_memory = importlib.import_module("induce_memory")

        self._select_memory = memory_management.select_memory
        self._format_trajectory = induce_memory.format_trajectory
        self._clients = induce_memory.CLIENT_DICT
        self._successful_prompt = induce_memory.SUCCESSFUL_SI
        self._failed_prompt = induce_memory.FAILED_SI

    def _commit(self) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(self.checkout), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return ""
        return result.stdout.strip()

    def load_bank(self) -> list[dict[str, Any]]:
        # Keep the newest record for a task when append-only reruns add a
        # replacement induction.  This also prevents the upstream selector's
        # first-match lookup from resurrecting an older memory record.
        latest: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for item in read_jsonl(self.bank_path):
            key = str(item.get("task_id", ""))
            if key not in latest:
                order.append(key)
            latest[key] = item
        return [latest[key] for key in order if memory_text(latest[key])]

    def select(self, *, task_id: str, query: str) -> Retrieval:
        # Upstream ranks every record it receives.  A capped or malformed
        # induction response can leave a record with no usable memory items;
        # passing those through lets retrieval select a record that injects an
        # empty guidance block.  Keep the upstream selector, but give it only
        # records that can actually provide guidance.
        bank = [item for item in self.load_bank() if memory_text(item)]
        selected = self._select_memory(
            n=1,
            reasoning_bank=bank,
            cur_query=query,
            task_id=str(task_id),
            cache_path=str(self.embeddings_path),
            prefer_model="openai",
        )
        item = selected[0] if selected else None
        return Retrieval(guidance=memory_text(item), selected=item)

    @staticmethod
    def observable_reasoning(trajectory: Iterable[dict[str, Any]]) -> tuple[list[str], list[str]]:
        """Map visible ALFWorld state into upstream think/action fields.

        No hidden model chain-of-thought is available or synthesized. The
        ``think`` field contains only the observation that preceded the action.
        """
        think_list: list[str] = []
        action_list: list[str] = []
        for transition in trajectory:
            think_list.append(
                "Observed ALFWorld state before choosing the action:\n"
                + str(transition.get("observation_before", ""))
            )
            action_list.append(str(transition.get("action", "")))
        return think_list, action_list

    def induce(self, row: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        think_list, action_list = self.observable_reasoning(row.get("trajectory") or [])
        formatted = self._format_trajectory(think_list, action_list)
        prompt = f"**Query:** {row['task']}\n\n**Trajectory:**\n{formatted}"
        final_observation = ""
        if row.get("trajectory"):
            final_observation = str(row["trajectory"][-1].get("observation", ""))
        status = "success" if bool(row.get("success")) else "fail"
        prompt += (
            "\n\n**ALFWorld objective correctness signal:**\n"
            + ("The task succeeded." if status == "success" else "The task failed.")
        )
        if final_observation:
            prompt += f"\n\n**Final environment observation:**\n{final_observation}"

        os.environ["REASONING_BANK_MAX_TOKENS"] = str(self.max_tokens)
        client = self._clients[self.model](model_name=self.model)
        generated, response = client.one_step_chat(
            prompt,
            system_msg=(
                self._successful_prompt if status == "success" else self._failed_prompt
            ),
            temperature=1.0,
        )
        generated = str(generated or "").strip()
        record = {
            "task_id": str(row["episode_index"]),
            "query": row["task"],
            "think_list": think_list,
            "action_list": action_list,
            "status": status,
            "memory_items": generated.split("\n\n") if generated else [],
            "template_id": row.get("task_family", "alfworld"),
            "global_task_index": int(row["episode_index"]) + 1,
            "game_file": row.get("game_file"),
            "adapter": "alfworld_observable_trajectory",
            "upstream_commit": self.commit,
        }
        return record, _response_metadata(response)
