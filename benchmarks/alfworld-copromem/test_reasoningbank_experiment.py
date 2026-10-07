from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from reasoningbank_adapter import ReasoningBankALFWorldAdapter, memory_text


class FakeUsage:
    def model_dump(self):
        return {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


class FakeResponse:
    id = "response-1"
    model = "test-model"
    usage = FakeUsage()


class FakeClient:
    calls = []

    def __init__(self, model_name: str):
        self.model_name = model_name

    def one_step_chat(self, text, system_msg=None, temperature=0.0):
        self.calls.append((text, system_msg, temperature))
        return "memory one\n\nmemory two", FakeResponse()


class FakeClients(dict):
    def __getitem__(self, key):
        return FakeClient


def bare_adapter() -> ReasoningBankALFWorldAdapter:
    adapter = ReasoningBankALFWorldAdapter.__new__(ReasoningBankALFWorldAdapter)
    adapter.model = "test-model"
    adapter.max_tokens = 1024
    adapter.embedding_model = "openai/text-embedding-3-small"
    adapter.commit = "ed80611-test"
    adapter._format_trajectory = lambda thoughts, actions: "\n".join(
        f"<think>{thought}</think><action>{action}</action>"
        for thought, action in zip(thoughts, actions)
    )
    adapter._clients = FakeClients()
    adapter._successful_prompt = "UPSTREAM SUCCESS"
    adapter._failed_prompt = "UPSTREAM FAILURE"
    return adapter


class ReasoningBankAdapterTests(unittest.TestCase):
    def test_memory_text_joins_upstream_items(self) -> None:
        self.assertEqual(
            "first\n\nsecond",
            memory_text({"memory_items": ["first", "second"]}),
        )
        self.assertEqual("", memory_text(None))

    def test_select_delegates_to_upstream_function(self) -> None:
        adapter = bare_adapter()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            adapter.bank_path = root / "bank.jsonl"
            adapter.embeddings_path = root / "embeddings.jsonl"
            adapter.bank_path.write_text(
                '{"task_id":"empty","memory_items":[]}\n'
                '{"task_id":"0","memory_items":["official memory"]}\n',
                encoding="utf-8",
            )
            calls = []

            def select_memory(**kwargs):
                calls.append(kwargs)
                return [kwargs["reasoning_bank"][0]]

            adapter._select_memory = select_memory
            result = adapter.select(task_id="1", query="put the mug away")

        self.assertEqual("official memory", result.guidance)
        self.assertEqual(["0"], [item["task_id"] for item in calls[0]["reasoning_bank"]])
        self.assertEqual(1, calls[0]["n"])
        self.assertEqual("openai", calls[0]["prefer_model"])
        self.assertEqual("1", calls[0]["task_id"])

    def test_pinned_upstream_selection_executes_through_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bank_path = root / "bank.jsonl"
            embeddings_path = root / "embeddings.jsonl"
            bank_path.write_text(
                '{"task_id":"0","memory_items":["upstream-selected"]}\n',
                encoding="utf-8",
            )
            embeddings_path.write_text(
                '{"id":"0","text":"prior","embedding":[1.0,0.0]}\n',
                encoding="utf-8",
            )
            adapter = ReasoningBankALFWorldAdapter(
                model="test-model",
                bank_path=bank_path,
                embeddings_path=embeddings_path,
            )
            module = __import__("memory_management")
            original = module.embed_query_with_openai
            module.embed_query_with_openai = lambda _query: np.asarray(
                [[1.0, 0.0]], dtype=np.float32
            )
            try:
                result = adapter.select(task_id="1", query="current")
            finally:
                module.embed_query_with_openai = original

        self.assertEqual("upstream-selected", result.guidance)
        self.assertEqual("0", result.selected["task_id"])

    def test_observable_mapping_does_not_invent_hidden_reasoning(self) -> None:
        thoughts, actions = ReasoningBankALFWorldAdapter.observable_reasoning(
            [{"observation_before": "A mug is visible.", "action": "take mug 1"}]
        )
        self.assertEqual(["take mug 1"], actions)
        self.assertIn("A mug is visible.", thoughts[0])

    def test_induction_uses_upstream_formatter_prompt_and_client(self) -> None:
        FakeClient.calls.clear()
        adapter = bare_adapter()
        row = {
            "episode_index": 2,
            "task": "put the mug on the table",
            "task_family": "pick_and_place_simple",
            "game_file": "/games/task/game.tw-pddl",
            "success": False,
            "trajectory": [
                {
                    "observation_before": "A mug is visible.",
                    "action": "take mug 1",
                    "observation": "You pick up the mug.",
                }
            ],
        }
        record, provider = adapter.induce(row)

        self.assertEqual("fail", record["status"])
        self.assertEqual(["memory one", "memory two"], record["memory_items"])
        self.assertEqual("pick_and_place_simple", record["template_id"])
        self.assertEqual("UPSTREAM FAILURE", FakeClient.calls[0][1])
        self.assertEqual(1.0, FakeClient.calls[0][2])
        self.assertIn("<think>", FakeClient.calls[0][0])
        self.assertEqual(15, provider["usage"]["total_tokens"])


if __name__ == "__main__":
    unittest.main()
