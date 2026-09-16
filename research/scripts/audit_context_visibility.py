"""Offline public-history truncation/repetition diagnostics; no causal labels."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest
from copromem.reflection_source import retry_settings
from copromem.stateful_source import context_for_step


def audit(root: Path) -> dict:
    store = RunStore(root)
    protocol = store.read("protocol", "preregistration")
    if protocol is None:
        raise IntegrityError("missing protocol")
    totals = Counter()
    by_episode = defaultdict(Counter)
    evidence = []
    previous = {}
    for path in sorted((root / "source_steps").glob("*.json")):
        step = store.read("source_steps", path.stem)
        episode_id = step["episode_id"]
        frame = store.read("stream_frames", f"{episode_id}-{step['step']:03d}")
        if frame is None:
            raise IntegrityError("missing public boundary frame")
        runtime_settings = (
            retry_settings(protocol, store, frame["task_id"])
            if protocol.get("context_version") == "public-history-retry-v3"
            else protocol
        )
        context = context_for_step(frame, runtime_settings, step["step"])
        handoff = store.read("public_handoffs", step["public_checkpoint_id"])
        if handoff is None or handoff["public_context"] != context:
            raise IntegrityError("context does not reproduce saved agent input")
        flags = {
            "boundaries": 1,
            "boundaries_omitting_earlier_history": int(
                context["omitted_history_entries"] > 0
            ),
            "boundaries_with_truncated_visible_entry": int(
                any(e["truncated"] for e in context["history"])
            ),
            "outputs_exceeding_4000_chars": int(len(step["public_output"]) > 4000),
            "programs_exceeding_6000_chars": int(len(step["code"]) > 6000),
            "exact_consecutive_program_repeat": int(
                episode_id in previous and previous[episode_id]["code"] == step["code"]
            ),
            "exact_consecutive_public_output_repeat": int(
                episode_id in previous
                and previous[episode_id]["public_output"] == step["public_output"]
            ),
        }
        # Preserve all old v1 reports exactly. For the new presentation, report
        # declared-cap diagnostics in addition to the fixed historical thresholds.
        if protocol.get("context_version", "v1") != "v1":
            flags["outputs_exceeding_declared_entry_cap"] = int(
                len(step["public_output"]) > protocol["history_output_chars"]
            )
            flags["programs_exceeding_declared_entry_cap"] = int(
                len(step["code"]) > protocol["history_program_chars"]
            )
        prior = previous.get(episode_id)
        if prior is not None and step["step"] != prior["step"] + 1:
            raise IntegrityError("noncontiguous episode steps")
        totals.update(flags)
        by_episode[episode_id].update(flags)
        evidence.append(
            {
                "step_id": path.stem,
                "source_step_sha256": digest(step),
                "public_checkpoint_id": step["public_checkpoint_id"],
                "omitted_history_entries": context["omitted_history_entries"],
                "visible_history_entries": len(context["history"]),
                "output_chars": len(step["public_output"]),
                **flags,
            }
        )
        previous[episode_id] = step
    return {
        "audit": "public-context-visibility-and-exact-repetition-v1"
        if protocol.get("context_version", "v1") == "v1"
        else "public-context-visibility-and-exact-repetition-v2",
        "cycle_id": protocol["cycle_id"],
        "totals": dict(totals),
        "by_episode": {key: dict(value) for key, value in by_episode.items()},
        "evidence": evidence,
        "model_calls": 0,
        "limitations": [
            "Retrospective descriptive counts, not a preregistered task metric or intervention effect.",
            "A repeated program/output can be appropriate; a truncated item may omit nothing useful.",
            "No labels for plan defects, predicate efficacy, or native task success are inferred.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.store)
    key = digest(report)
    RunStore(args.store).write("context_audits", key, report)
    print(
        json.dumps(
            {"report_id": key, **{k: v for k, v in report.items() if k != "evidence"}},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
