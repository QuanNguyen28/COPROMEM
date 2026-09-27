"""Restart semantics for the CoProMem fixed/dynamic evaluation streams."""
from __future__ import annotations

import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("fixed_dynamic_runner", ROOT / "scripts" / "run_corrected_fixed_dynamic_v2.py")
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(RUNNER)


class _Adapter:
    def __init__(self, state: dict[str, object]) -> None:
        self.state = state
    def semantic_state_hash(self) -> str:
        return RUNNER.digest(self.state)


class CoProMemResumeSemanticsTest(unittest.TestCase):
    def test_restored_dynamic_stream_is_checked_against_its_snapshot(self) -> None:
        initial = {"episodes": ["acquisition"]}
        updated = {"episodes": ["acquisition", "post-trial-update"]}
        RUNNER.assert_copromem_clone_states(
            fixed=_Adapter(initial), dynamic={1: _Adapter(updated), 2: _Adapter(initial)},
            initial_hash=RUNNER.digest(initial), restored_dynamic_states={1: updated},
        )

    def test_restored_dynamic_stream_cannot_silently_diverge(self) -> None:
        initial = {"episodes": ["acquisition"]}
        expected = {"episodes": ["acquisition", "post-trial-update"]}
        with self.assertRaisesRegex(RuntimeError, "trial 1"):
            RUNNER.assert_copromem_clone_states(
                fixed=_Adapter(initial), dynamic={1: _Adapter({"episodes": ["wrong"]})},
                initial_hash=RUNNER.digest(initial), restored_dynamic_states={1: expected},
            )


if __name__ == "__main__":
    unittest.main()
