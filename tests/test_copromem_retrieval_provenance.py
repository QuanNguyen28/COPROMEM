from __future__ import annotations
import unittest
from src.copromem.appworld_comparison_adapter import CoProMemAppWorldAdapter, TrialInput

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

if __name__ == "__main__": unittest.main()
