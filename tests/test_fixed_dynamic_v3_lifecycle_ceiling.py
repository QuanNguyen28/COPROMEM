"""Regression coverage for the v3 lifecycle-only context amendment."""
from __future__ import annotations

import os
import pathlib
import tempfile
import unittest
from unittest import mock

from research.official_pilot.locked_openrouter import (
    AppendOnlyLedger, ContextCeilingTermination, LockedChatCompletions, MODEL,
)


class LifecycleCeilingTest(unittest.TestCase):
    def test_lifecycle_only_ceiling_does_not_change_executor_ceiling(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            ledger = AppendOnlyLedger(root / "ledger.jsonl", 10.0)
            with mock.patch.dict(os.environ, {"OFFICIAL_PILOT_LIFECYCLE_INPUT_TOKEN_CEILING": "65536"}):
                with mock.patch("research.official_pilot.locked_openrouter.count_chat_tokens", return_value=70_000):
                    with self.assertRaises(ContextCeilingTermination) as lifecycle:
                        LockedChatCompletions("unused", ledger, root / "progress.jsonl", "reme_lifecycle").create(
                            model=MODEL, messages=[{"role": "user", "content": "x"}])
                    with self.assertRaises(ContextCeilingTermination) as executor:
                        LockedChatCompletions("unused", ledger, root / "progress.jsonl", "executor:no_memory").create(
                            model=MODEL, messages=[{"role": "user", "content": "x"}])
            self.assertEqual(lifecycle.exception.ceiling, 65_536)
            self.assertEqual(executor.exception.ceiling, 32_768)
            self.assertFalse((root / "ledger.jsonl").exists(), "pre-dispatch rejection must not reserve")


if __name__ == "__main__":
    unittest.main()
