"""Write the terminal artifact for a fail-closed exploratory route failure."""
from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, "src")
from copromem.checkpoints import RunStore, digest


ROOT = Path("artifacts/research/reme_copromem_comparison/openrouter_failure_informed_exploratory_pilot")


def main() -> None:
    invalid = []
    for path in sorted((ROOT / "locked_transport").glob("*.json")):
        item = json.loads(path.read_text(encoding="utf-8"))
        if not all(bool(value) for value in item["validation"].values()):
            invalid.append({"key": path.stem, "response_model": item["response_model"], "provider": item["provider"], "finish_reason": item["finish_reason"], "tool_call_count": item["tool_call_count"], "reasoning_tokens": item["usage"]["reasoning_tokens"], "actual_usd": item["actual_usd"], "validation": item["validation"]})
    if len(invalid) != 1:
        raise RuntimeError("expected exactly one terminal locked-route fidelity failure")
    terminal = {"status": "locked_route_fidelity_failure", "reason": "A frozen voluntary-native-tool decomposition request completed without the required tool call; no retry, fallback, or request-shape change is permitted.", "invalid_transport_records": invalid, "evaluation_started": False}
    RunStore(ROOT).write("pilot_terminal", "locked_route_failure", {"sha256": digest(terminal), "terminal": terminal})
    print(json.dumps({"status": terminal["status"], "terminal_sha256": digest(terminal)}))


if __name__ == "__main__":
    main()
