from __future__ import annotations
import unittest
import json
import pathlib
import tempfile
from copromem.benchmarks.appworld.adapter import CoProMemAppWorldAdapter, TrialInput
import copromem.experiments.reme_copromem.config as v4
from copromem.experiments.reme_copromem.runner import digest

class ProvenanceTest(unittest.TestCase):
    def test_exact_offline_reproduction_and_tamper_rejection(self) -> None:
        adapter=CoProMemAppWorldAdapter()
        state=adapter.export_state()
        trial=TrialInput("task-x", "Find the current account balance.", "appworld", base_prompt="Find the current account balance.")
        guidance, provenance=adapter.retrieve_with_provenance(trial, 1)
        self.assertEqual(guidance, CoProMemAppWorldAdapter.reproduce_retrieval(state, provenance["task_input"], provenance))
        changed=dict(provenance); changed["guidance_sha256"]="0"*64
        with self.assertRaises(ValueError): CoProMemAppWorldAdapter.reproduce_retrieval(state, provenance["task_input"], changed)
    def test_empty_intent_and_duplicate_retrieval_fail_closed(self) -> None:
        adapter=CoProMemAppWorldAdapter(); blank=TrialInput("x", "", "appworld")
        with self.assertRaises(ValueError): adapter.retrieve_with_provenance(blank, 1)
        trial=TrialInput("x", "Inspect a record.", "appworld", base_prompt="Inspect a record.")
        adapter.retrieve_with_provenance(trial, 1)
        with self.assertRaises(RuntimeError): adapter.retrieve_with_provenance(trial, 1)

    def test_retrieval_restart_uses_persisted_pre_state_and_rejects_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            previous, v4.RUN = v4.RUN, pathlib.Path(directory)
            try:
                fixed = CoProMemAppWorldAdapter(); before = fixed.semantic_state_hash()
                callback = v4.copro_retrieval("copromem_fixed", fixed, "task-x", 1)
                guidance = callback("Inspect a record.", "appworld", {})
                self.assertEqual(before, fixed.semantic_state_hash())  # fixed reads do not mutate semantic state
                path = v4.RUN / "retrieval/copromem_fixed/task-x/trial-1.json"
                stored = json.loads(path.read_text())
                self.assertIn("pre_state", stored["provenance"])
                # A restored dynamic stream has exactly the state expected for
                # this trajectory and can reuse the durable record with no new
                # retrieval/decomposition/provider callback.
                dynamic = CoProMemAppWorldAdapter(); dynamic.clone_from_state(stored["provenance"]["pre_state"])
                dynamic.retrieve_with_provenance = lambda *_a, **_k: self.fail("cached restart must not retrieve")
                resumed = v4.copro_retrieval("copromem_fixed", dynamic, "task-x", 1)("Inspect a record.", "appworld", {})
                self.assertEqual(guidance, resumed)
                stored["provenance"]["pre_state_sha256"] = "0" * 64
                path.write_text(json.dumps(stored), encoding="utf-8")
                with self.assertRaises(RuntimeError):
                    v4.copro_retrieval("copromem_fixed", dynamic, "task-x", 1)("Inspect a record.", "appworld", {})
            finally:
                v4.RUN = previous

    def test_artifact_reconciliation_uses_runner_canonical_unicode_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "trial-1.json"
            history = [{"role": "user", "content": "Hà Nội — café"}, {"role": "assistant", "content": "print('✓')"}]
            row = {"arm": "no_memory", "task_id": "task-x", "trial_id": 1, "history": history,
                   "history_sha256": digest(history), "after_score": 1.0}
            # Deliberately indented and ASCII-escaped on disk: reload must
            # canonicalize the object rather than hash file formatting.
            path.write_text(json.dumps(row, ensure_ascii=True, indent=7), encoding="utf-8")
            self.assertEqual(v4.verify_existing_artifact(path, "no_memory", "task-x", 1)["history_sha256"], digest(history))
            row["history"][0]["content"] = "tampered"
            path.write_text(json.dumps(row, ensure_ascii=False, indent=1), encoding="utf-8")
            with self.assertRaises(RuntimeError): v4.verify_existing_artifact(path, "no_memory", "task-x", 1)

if __name__ == "__main__": unittest.main()
