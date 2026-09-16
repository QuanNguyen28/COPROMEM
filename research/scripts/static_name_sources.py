"""Fourteen fixed public action/local-error records with exact context binding."""

from __future__ import annotations

import runpy
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest
from copromem.stateful_adapter import verify_prefix_pair
from copromem.stateful_effect import error_indices, origin_checkpoint

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CHECK = runpy.run_path(str(HERE / "static_name_check.py"))
PUBLIC = runpy.run_path(str(HERE / "public_presence.py"))


def require(value: bool, message: str) -> None:
    if not value:
        raise IntegrityError(message)


def bind_context(
    source_before: dict,
    probe_before: dict,
    source_checkpoint: str,
    probe_checkpoint: str,
    output: str,
    names: list[str],
) -> dict:
    require(
        source_checkpoint == probe_checkpoint,
        "public context belongs to another planner/checkpoint",
    )
    verify_prefix_pair(
        source_before, probe_before, expected_error_indices=error_indices(source_before)
    )
    return PUBLIC["parse_output"](output, names)


def collect() -> tuple[list[dict], dict]:
    presence = RunStore(ROOT / "artifacts/research/cycle21_public_presence")
    audit = runpy.run_path(str(HERE / "audit_public_presence.py"))["audit"](presence)
    require(
        audit["report_digest"]
        == "bacbfce08a8ebb4b9983a89c84e95ef65baf45d0fb7b459d929d820fb0527109"
        and audit["primary_metric"] == 3,
        "registered presence context audit changed",
    )
    protocol = presence.read("protocol", "preregistration")
    boundaries = [presence.read("boundaries", key) for key in protocol["boundary_ids"]]
    registry = {(b["episode"], b["index"]): (i, b) for i, b in enumerate(boundaries)}
    descriptors = []
    old = RunStore(ROOT / "artifacts/research/cycle13_procedural_diff")
    for path in sorted((old.root / "variant_results").glob("*.json")):
        variant = old.read("variant_results", path.stem)
        proposal = old.read("variant_proposals", path.stem)
        for cell in variant["cells"]:
            origin = next(
                b for b in boundaries if b["episode"] == cell["origin_episode"]
            )
            descriptors.append(
                (
                    old,
                    cell["cell_id"],
                    origin,
                    proposal["program"],
                    cell["checkpoint_id"],
                    {
                        "source": "cycle13",
                        "variant_digest": digest(variant),
                        "proposal_digest": digest(proposal),
                        "cell_digest": digest(cell),
                    },
                )
            )
    require(len(descriptors) == 10, "all ten variant/origin cells required")
    for i, boundary in enumerate(boundaries):
        cell = presence.read("observation_cells", f"c21-control-{i:02d}")
        descriptors.append(
            (
                presence,
                cell["cell_id"],
                boundary,
                boundary["origin"]["step"]["code"],
                cell["checkpoint_digest"],
                {"source": "cycle21", "cell_digest": digest(cell)},
            )
        )
    new = RunStore(ROOT / "artifacts/research/cycle18_bound_effects")
    cell = new.read("effect_cells", "c18b-edit-02")
    candidate = new.read("effect_candidates", cell["candidate_id"])
    require(
        digest(candidate) == cell["candidate_id"], "new repaired program source changed"
    )
    descriptors.append(
        (
            new,
            cell["cell_id"],
            boundaries[2],
            candidate["proposal"]["program"],
            cell["checkpoint_digest"],
            {
                "source": "cycle18",
                "cell_digest": digest(cell),
                "candidate_digest": digest(candidate),
            },
        )
    )
    require(
        len(descriptors) == 14, "registered corpus must contain all fourteen actions"
    )
    rows = []
    for source, key, boundary, program, checkpoint_id, evidence in descriptors:
        index = boundary["index"]
        probe_index, stored_boundary = registry[(boundary["episode"], index)]
        require(
            digest(boundary) == digest(stored_boundary), "context boundary replacement"
        )
        probe_key = f"c21-probe-{probe_index:02d}"
        observation = presence.read("observation_cells", probe_key)
        source_before = source.read("stream_frames", key + "-live-000")
        before = presence.read("stream_frames", probe_key + "-live-000")
        after = presence.read("stream_frames", probe_key + "-live-001")
        require(
            observation["gate_passed"]
            and observation["checkpoint_digest"]
            == digest(origin_checkpoint(boundary["origin"])),
            "context gate/checkpoint mismatch",
        )
        envelope = bind_context(
            source_before,
            before,
            checkpoint_id,
            observation["checkpoint_digest"],
            after["results"][-1]["output"],
            boundary["construction"]["names"],
        )
        require(
            envelope == observation["public_envelope"], "parsed public envelope changed"
        )
        worker = source.read("worker_results", key + "-live")
        request = source.read("worker_requests", key + "-live")
        require(
            worker["request_id"] == digest(request)
            and [r["program"] for r in worker["results"]] == request["actions"]
            and request["actions"][:index]
            == boundary["origin"]["prefix_request"]["actions"]
            and request["actions"][index] == program
            and request["task_id"] == boundary["original_request"]["task_id"],
            "action not bound to exact saved execution",
        )
        output = worker["results"][index]["output"]
        public = {"program": program, "envelope": envelope}
        rows.append(
            {
                "origin_episode": boundary["episode"],
                "action_index": index,
                "source_cell": key,
                "source_store": str(source.root),
                "source_evidence": evidence,
                "checkpoint_digest": checkpoint_id,
                "public_context_cell": probe_key,
                "public_context_digest": digest(envelope),
                "public_input": public,
                "public_input_digest": digest(public),
                "public_action_output": output,
                "local_label": CHECK["local_label"](output),
                "final_native_success_audit_only": source.read(
                    "native_evaluation", key + "-live"
                )["native_success"],
            }
        )
    return rows, audit
