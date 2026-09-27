from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from research.official_pilot.reme_bank import _assert_clone_equivalent, semantic_bank_hash
from research.official_pilot.five_arm_runner import ReMeService


class ReMeCloneSemanticTest(unittest.TestCase):
    def test_upstream_reme_base_url_is_endpoint_concatenation_safe(self) -> None:
        service = object.__new__(ReMeService); service.port = 18201
        self.assertEqual(service.base_url, "http://127.0.0.1:18201/")

    def test_float32_round_trip_preserves_semantic_bank(self) -> None:
        source = [{"memory_id": "m1", "content": "stable", "metadata": {"a": 1}, "vector": [0.1, 0.2]}]
        clone = [{"memory_id": "m1", "content": "stable", "metadata": {"a": 1}, "vector": [0.10000000149, 0.2]}]
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw); left, right = root / "left.jsonl", root / "right.jsonl"
            left.write_text(json.dumps(source[0]) + "\n"); right.write_text(json.dumps(clone[0]) + "\n")
            _assert_clone_equivalent(left, right)
            self.assertEqual(semantic_bank_hash(left), semantic_bank_hash(right))

    def test_content_change_fails_even_when_vector_is_close(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw); left, right = root / "left.jsonl", root / "right.jsonl"
            left.write_text(json.dumps({"memory_id": "m1", "content": "a", "vector": [0.1]}) + "\n")
            right.write_text(json.dumps({"memory_id": "m1", "content": "b", "vector": [0.1]}) + "\n")
            with self.assertRaises(RuntimeError): _assert_clone_equivalent(left, right)


if __name__ == "__main__": unittest.main()
