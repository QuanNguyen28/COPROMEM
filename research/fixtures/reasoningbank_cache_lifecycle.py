"""Unchanged upstream function bodies, toy embeddings, no cloud/module startup.

This is a source-level behavioral fixture, NOT native import, learned retrieval,
embedding-model reproduction, or a benchmark score. Run only in the probe image.
"""

import ast
import hashlib
import json
import logging
import os
import platform
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple  # noqa: UP035 -- upstream annotations

import torch
import torch.nn.functional as F

SOURCE_SHA256 = "ac40e71d216668ed5af49bb5c94b77cf7906ef0149c74e4e55ade792e88fd4e2"
FUNCTIONS = {
    "l2_normalize",
    "load_cached_embeddings",
    "get_detailed_instruct",
    "select_memory",
    "screening",
}


def main():
    source_path = Path("/vendor/WebArena/memory_management.py")
    raw = source_path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_SHA256
    source = raw.decode("utf-8")
    nodes = [
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS
    ]
    assert {node.name for node in nodes} == FUNCTIONS
    embedding_calls = []
    qwen_dimensions = [3]

    def gemini_stub(query, dimensionality=3072):
        embedding_calls.append(
            {"backend": "gemini", "instruction": query.startswith("Instruct:")}
        )
        return torch.tensor([[1.0, 0.0, 0.0]])

    def qwen_stub(query):
        embedding_calls.append({"backend": "qwen", "instruction": False})
        return torch.tensor([[1.0] + [0.0] * (qwen_dimensions[0] - 1)])

    namespace = {
        "os": os,
        "json": json,
        "torch": torch,
        "F": F,
        "Dict": Dict,  # noqa: UP006 -- preserve upstream annotation bindings
        "List": List,  # noqa: UP006
        "Tuple": Tuple,  # noqa: UP006
        "logger": logging.getLogger("reasoningbank-fixture"),
        "embed_query_with_gemini": gemini_stub,
        "embed_query_with_qwen": qwen_stub,
    }
    # No function body is edited. Only reviewed definitions are compiled, so
    # upstream import-time Vertex/GenAI initialization is intentionally bypassed.
    exec(  # noqa: S102 -- reviewed hash-pinned definitions, isolated container
        compile(ast.Module(body=nodes, type_ignores=[]), str(source_path), "exec"),
        namespace,
    )
    select = namespace["select_memory"]
    screen = namespace["screening"]
    checks = []

    with tempfile.TemporaryDirectory(prefix="reasoningbank-cache-") as task_tmp:
        base = Path(task_tmp)

        def cache(name, rows):
            path = base / (name + ".jsonl")
            path.write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            return str(path)

        def record(key, vector):
            return {"id": key, "text": "authored toy query", "embedding": vector}

        path = str(base / "missing.jsonl")
        embedding_calls.clear()
        assert select(1, [], "toy current query", "new", path) == {}
        rows = [json.loads(line) for line in Path(path).read_text().splitlines()]
        assert [row["id"] for row in rows] == ["new"]
        assert embedding_calls == [{"backend": "gemini", "instruction": False}]
        checks.append(
            "missing cache created; current query appended; empty return is dict; one embedding stub call"
        )

        path = cache("fresh-excluded", [record("old", [0, 1, 0])])
        embedding_calls.clear()
        scores, ids = screen("toy current query", path, "current", "gemini")
        assert ids == ["old"] and len(scores) == 1
        assert embedding_calls == [
            {"backend": "gemini", "instruction": False},
            {"backend": "gemini", "instruction": True},
        ]
        checks.append(
            "just-appended current query is not ranked in the same call; nonempty cache uses two embedding stub calls"
        )

        bank = [
            {"task_id": "old", "memory": "old toy memory"},
            {"task_id": "current", "memory": "current toy memory"},
        ]
        assert select(1, bank, "toy repeated query", "current", path) == [bank[1]]
        checks.append(
            "a previously cached same-task entry can be retrieved on a later call"
        )

        path = cache(
            "stale", [record("absent", [1, 0, 0]), record("present", [0, 1, 0])]
        )
        assert select(1, [{"task_id": "present"}], "toy", "new", path) == []
        checks.append(
            "a stale top-ranked cache ID consumes the slot without bank backfill"
        )

        path = cache(
            "duplicates", [record("same", [1, 0, 0]), record("same", [1, 0, 0])]
        )
        first, second = (
            {"task_id": "same", "memory": "first"},
            {"task_id": "same", "memory": "second"},
        )
        assert select(2, [first, second], "toy", "new", path) == [first, first]
        checks.append("duplicate cache IDs repeat the first matching bank entry")

        path = cache("integer-id", [record(1, [1, 0, 0])])
        assert select(1, [{"task_id": 1}], "toy", "new", path) == []
        checks.append(
            "ranked IDs become strings; integer bank IDs do not match automatically"
        )

        many = [record(str(index), [1, 0, 0]) for index in range(12)]
        path = cache("large-n", many)
        assert (
            len(
                select(12, [{"task_id": row["id"]} for row in many], "toy", "new", path)
            )
            == 12
        )
        checks.append("n above ten logs an error but is not capped")

        path = cache("qwen-empty", [])
        embedding_calls.clear()
        assert screen("toy", path, "new", "Qwen") == ([], [])
        assert embedding_calls == [{"backend": "qwen", "instruction": False}]
        checks.append("empty Qwen cache uses only its initial embedding stub call")

        path = cache("qwen-nonempty", [record("old", [0, 1, 0])])
        embedding_calls.clear()
        screen("toy", path, "new", "Qwen")
        assert embedding_calls == [
            {"backend": "qwen", "instruction": False},
            {"backend": "gemini", "instruction": True},
        ]
        checks.append(
            "nonempty Qwen path still invokes the Gemini ranking embedding stub"
        )

        path = cache("dimension-mismatch", [record("old", [0, 1, 0])])
        qwen_dimensions[0] = 2
        assert screen("toy", path, "new", "Qwen")[1] == ["old"]
        rejected = False
        try:
            namespace["load_cached_embeddings"](path)
        except (ValueError, RuntimeError):
            rejected = True
        assert rejected
        checks.append(
            "synthetic mixed-dimension append can pass current scoring then make next cache load fail"
        )

    print(
        json.dumps(
            {
                "kind": "unchanged source-function-body fixture with deterministic toy embeddings",
                "source_sha256": SOURCE_SHA256,
                "functions": sorted(FUNCTIONS),
                "function_source_sha256": {
                    node.name: hashlib.sha256(
                        ast.get_source_segment(source, node).encode()
                    ).hexdigest()
                    for node in nodes
                },
                "python": platform.python_version(),
                "torch": torch.__version__,
                "checks": checks,
                "passed": len(checks),
                "native_module_imported": False,
                "real_embeddings": False,
                "paid_calls": 0,
                "benchmark_episodes": 0,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
