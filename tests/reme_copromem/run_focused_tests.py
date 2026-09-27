#!/usr/bin/env python3
"""Dependency-free focused regression entrypoint for v4 resume repair."""
from __future__ import annotations
import pathlib
import tempfile
import unittest
from tests.reme_copromem.test_reme_bank import (
    test_reme_initial_bank_uses_pinned_legacy_summary_add_dump_load_contract,
    test_v4_progress_callback_is_unary_and_persisted_restart_skips_provider_work,
)
from tests.reme_copromem.test_copromem_retrieval_provenance import ProvenanceTest

def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        test_reme_initial_bank_uses_pinned_legacy_summary_add_dump_load_contract(root / "first")
        test_v4_progress_callback_is_unary_and_persisted_restart_skips_provider_work(root / "second")
    result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(ProvenanceTest))
    if not result.wasSuccessful(): raise SystemExit(1)
    print("focused-v4-tests=passed")

if __name__ == "__main__": main()
