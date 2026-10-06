from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from run_reme_experiment import LegacyRemeService


class LegacyRemeServiceTests(unittest.TestCase):
    def service(self, root: Path) -> LegacyRemeService:
        return LegacyRemeService(
            root / "logs",
            "test-model",
            8999,
            state_dir=root,
            workspace_id="alfworld-test",
        )

    def test_record_retrieved_matches_upstream_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self.service(Path(temp_dir))
            calls = []

            def post(path, payload, timeout=240):
                calls.append((path, payload, timeout))
                return {"metadata": {"updated": 1}}

            service.post = post
            result = service.record_retrieved(
                [{"memory_id": "m1", "memory_type": "task"}], True
            )

        self.assertEqual("/record_task_memory", calls[0][0])
        self.assertEqual("alfworld-test", calls[0][1]["workspace_id"])
        self.assertEqual("m1", calls[0][1]["memory_dicts"][0]["memory_id"])
        self.assertNotIn("memory_list", calls[0][1])
        self.assertTrue(calls[0][1]["update_utility"])
        self.assertEqual(1, result["metadata"]["updated"])

    def test_checkpoint_and_restore_use_upstream_vector_store_actions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = self.service(root)
            calls = []

            def dump_post(path, payload, timeout=240):
                calls.append((path, payload))
                dump_dir = Path(payload["path"])
                dump_dir.mkdir(parents=True, exist_ok=True)
                (dump_dir / "alfworld-test.jsonl").write_text(
                    '{"memory_id":"m1","memory_type":"task"}\n',
                    encoding="utf-8",
                )
                return {"metadata": {"action_result": "1"}}

            service.post = dump_post
            result = service.checkpoint()
            self.assertEqual(1, result["event"]["memory_count"])
            self.assertTrue(service.snapshot_path.is_file())
            self.assertEqual("dump", calls[0][1]["action"])
            self.assertEqual("alfworld-test", calls[0][1]["workspace_id"])

            restored = self.service(root)
            restore_calls = []

            def load_post(path, payload, timeout=240):
                restore_calls.append((path, payload))
                return {"metadata": {"action_result": "1"}}

            restored.post = load_post
            restore_result = restored.restore_snapshot()

        self.assertEqual(1, restore_result["event"]["memory_count"])
        self.assertEqual("/vector_store", restore_calls[0][0])
        self.assertEqual("load", restore_calls[0][1]["action"])
        self.assertEqual(str(restored.snapshot_dir), restore_calls[0][1]["path"])

    def test_corrupt_snapshot_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = self.service(root)
            service.snapshot_dir.mkdir(parents=True, exist_ok=True)
            service.snapshot_path.write_text("not-json\n", encoding="utf-8")
            service.post = lambda *_args, **_kwargs: self.fail(
                "a corrupt snapshot must not be sent to ReMe"
            )
            with self.assertRaisesRegex(RuntimeError, "invalid REmE snapshot"):
                service.restore_snapshot()

    def test_fresh_run_loads_an_explicit_empty_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = self.service(root)
            calls = []
            service.post = lambda path, payload, timeout=240: (
                calls.append((path, payload))
                or {"metadata": {"action_result": "{'size': 0}"}}
            )
            result = service.restore_snapshot()

        self.assertEqual("memory_bank_started_empty", result["event"]["event"])
        self.assertEqual("load", calls[0][1]["action"])
        self.assertEqual(str(service.snapshot_dir), calls[0][1]["path"])

    def test_historical_summary_memories_are_recovered_without_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = self.service(root)
            rows = [
                {
                    "arm": "legacy_reme",
                    "reme_summary": {
                        "response": {
                            "metadata": {
                                "memory_list": [
                                    {
                                        "workspace_id": "alfworld-test",
                                        "memory_id": "m1",
                                        "memory_type": "task",
                                        "when_to_use": "cleaning tasks",
                                        "content": "Use the sink before placing the object.",
                                    }
                                ],
                                "update_result": {"inserted_count": 1, "deleted_count": 0},
                            }
                        }
                    },
                }
            ]
            count = service.recover_snapshot_from_rows(rows)
            recovered = service.snapshot_path.read_text(encoding="utf-8")

        self.assertEqual(1, count)
        self.assertIn('"memory_id": "m1"', recovered)
        self.assertEqual(
            "memory_bank_recovered_from_episode_rows",
            service.events[0]["event"],
        )


if __name__ == "__main__":
    unittest.main()
