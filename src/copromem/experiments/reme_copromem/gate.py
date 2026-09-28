"""Audit the train warm start before a continuous CoProMem run."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from ...benchmarks.appworld.adapter import CoProMemAppWorldAdapter


def build_gate(state: dict[str, Any], trajectories: list[dict[str, Any]]) -> dict[str, Any]:
    learning = state.get("learning", {})
    expected = {str(row["acquisition_identity"]) for row in trajectories}
    observed = set(learning.get("episodes", {}))
    schemas = learning.get("schemas", ())
    procedures = learning.get("procedures", ())
    return {
        "protocol": "continuous_copromem_v5",
        "bank_sha256": CoProMemAppWorldAdapter._digest(state),
        "provider_calls": 0,
        "episode_count": len(observed),
        "candidate_count": sum(item["status"] == "candidate" for item in schemas),
        "usable_schema_count": sum(item["status"] == "provisional" for item in schemas),
        "usable_procedure_count": sum(item["status"] == "provisional" for item in procedures),
        "passed": state.get("version") == 5 and observed == expected,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--acquisition", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    state = json.loads(args.state.read_text(encoding="utf-8"))
    source = json.loads(args.acquisition.read_text(encoding="utf-8"))
    rows = source["trajectories"] if isinstance(source, dict) else source
    gate = build_gate(state, rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(gate, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": gate["passed"],
                      "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                      "episode_count": gate["episode_count"]}))


if __name__ == "__main__":
    main()
