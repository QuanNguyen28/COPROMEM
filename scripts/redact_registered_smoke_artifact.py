"""Remove task-private native outputs from the registered smoke artifact."""
from __future__ import annotations

import json
from pathlib import Path


PATH = Path("artifacts/research/reme_copromem_comparison/direct_deepseek_successor_smoke/smoke_result.json")


def redact_calls(calls: list[dict]) -> None:
    for call in calls:
        output = call.pop("output", None)
        if isinstance(output, dict):
            call["native_action_ok"] = bool(output.get("ok"))
            call["native_action_completed"] = bool(output.get("completed"))
        elif output is not None:
            call["native_action_ok"] = False
            call["native_action_completed"] = False


def main() -> None:
    data = json.loads(PATH.read_text(encoding="utf-8"))
    for item in data.get("acquisition", []):
        redact_calls(item.get("calls", []))
    for item in data.get("arms", {}).values():
        redact_calls(item.get("calls", []))
    data["artifact_redaction"] = "Raw native outputs removed; they can contain task-private state."
    PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
