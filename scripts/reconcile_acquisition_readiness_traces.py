"""Append-only hash reconciliation for an already-terminal readiness run."""
from pathlib import Path
import sys

sys.path.insert(0, "src")
from copromem.checkpoints import RunStore, digest

ROOT = Path("artifacts/research/reme_copromem_comparison/acquisition_readiness")

def main() -> None:
    store = RunStore(ROOT)
    for start in sorted((ROOT / "acquisition_start").glob("*.json")):
        key = start.stem
        actions = [store.read("acquisition_actions", p.stem) for p in sorted((ROOT / "acquisition_actions").glob(f"{key}--*.json"))]
        store.write("trace_reconciliation", key, {"raw_trajectory_sha256": digest({"start": store.read("acquisition_start", key), "actions": actions}),
            "action_count": len(actions), "basis": "immutable start/action journal; no model or native replay"})

if __name__ == "__main__": main()
