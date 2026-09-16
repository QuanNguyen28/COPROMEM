"""Audited effect provenance adapter; only source text and labels reach the miner."""

from __future__ import annotations

import runpy
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest
from copromem.stateful_effect import origin_checkpoint

SOURCES = {
    "c13": (
        "cycle13_procedural_diff",
        "audit_procedural_diff.py",
        "3b804f5a064696081627852d0eb3046e761a7dae49ec410d8ecb92d1da2a166d",
    ),
    "c17": (
        "cycle17_boundary_effects",
        "audit_boundary_effects.py",
        "34d849a67422629d7c6c6b35761794ed44c21765928d61fa1ff9856de415264c",
    ),
    "c18": (
        "cycle18_bound_effects",
        "audit_bound_effects.py",
        "41f762eab2b0f87b9088e6c9234986d00c4b94245b6d87aa8a09b3bf7a6b5465",
    ),
}
TRAIN_AST = {
    "c13": "45c299c43e68a9e627fc074073eff39dc0118e137d6f0b66afb59572c7338db3",
    "c18": "bc8fb266dc1bd4bab8c85c1a2ac0258abb4006915b0a0a9c990f64fac3ace2a1",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise IntegrityError(message)


def public_action(
    request: dict, worker: dict, native: dict, index: int, expected_program: str
) -> dict:
    """Verify execution identity, then strip everything except public code/label."""
    require(
        type(index) is int
        and 0 <= index < len(request["actions"])
        and worker["request_id"] == digest(request)
        and worker["task_id"] == native["task_id"] == request["task_id"]
        and [row["program"] for row in worker["results"]] == request["actions"]
        and request["actions"][index] == expected_program
        and type(native["native_success"]) is bool,
        "public action/native label do not match the audited source execution",
    )
    return {"program": expected_program, "label": native["native_success"]}


def example(
    store: RunStore,
    cell: str,
    origin: str,
    index: int,
    program: str,
    evidence: dict,
    *,
    eligible: bool = True,
    exclusion=None,
) -> dict:
    public = public_action(
        store.read("worker_requests", cell + "-live"),
        store.read("worker_results", cell + "-live"),
        store.read("native_evaluation", cell + "-live"),
        index,
        program,
    )
    return {
        "origin_episode": origin,
        "action_index": index,
        "public": public,
        "public_digest": digest(public),
        "evidence": evidence,
        "eligible": eligible,
        "exclusion": exclusion,
    }


def collect(root: Path) -> tuple[list[dict], list[dict], dict]:
    """All 48 registered cells, with serial source audits and four training rows."""
    stores, reports, audits = {}, {}, {}
    for name, (folder, script, report_id) in SOURCES.items():
        store = stores[name] = RunStore(root / "artifacts/research" / folder)
        report = reports[name] = store.read("reports", report_id)
        require(
            report is not None and digest(report) == report_id, "source report changed"
        )
        audit = runpy.run_path(str(Path(__file__).with_name(script)))["audit"]
        audits[name] = audit(store, report_id) if name == "c13" else audit(store)
    diagnostic, training = [], []
    store = stores["c13"]
    protocol = store.read("protocol", "preregistration")
    retained = None
    for path in sorted((store.root / "variant_results").glob("*.json")):
        variant = store.read("variant_results", path.stem)
        proposal = store.read("variant_proposals", path.stem)
        origins = protocol["source_protocol"]["pairs"][variant["pair_index"]]
        for cell, origin in zip(variant["cells"], origins, strict=True):
            index = len(origin["prefix_request"]["actions"])
            require(
                cell["origin_episode"] == origin["episode"]["episode_id"]
                and digest(origin_checkpoint(origin)) == cell["checkpoint_id"],
                "variant origin/checkpoint identity mismatch",
            )
            row = example(
                store,
                cell["cell_id"],
                cell["origin_episode"],
                index,
                proposal["program"],
                {
                    "source": "c13",
                    "report": SOURCES["c13"][2],
                    "variant_key": path.stem,
                    "variant_digest": digest(variant),
                    "cell_id": cell["cell_id"],
                    "cell_digest": digest(cell),
                    "checkpoint_digest": cell["checkpoint_id"],
                },
            )
            diagnostic.append(row)
            if (
                variant["program_ast_digest"] == TRAIN_AST["c13"]
                and not origin["episode"]["native_evaluation"]["native_success"]
            ):
                require(
                    retained is None and row["public"]["label"],
                    "ambiguous c13 training repair",
                )
                retained = (row, origin)
    require(
        len(diagnostic) == 10 and retained is not None, "incomplete c13 denominator"
    )
    old_source = RunStore(root / "artifacts/research/cycle17_all_boundary_screen")
    new_training = None
    for name in ("c17", "c18"):
        store = stores[name]
        for cell in reports[name]["rows"]:
            require(
                store.read("effect_cells", cell["cell_id"]) == cell,
                "cell report mismatch",
            )
            candidate = (
                old_source.read("candidates", cell["candidate_id"])
                if name == "c17"
                else store.read("effect_candidates", cell["candidate_id"])
            )
            require(
                digest(candidate) == cell["candidate_id"], "candidate digest mismatch"
            )
            program = (
                candidate["origin"]["step"]["code"]
                if cell["factual"]
                else candidate["proposal"]["program"]
            )
            row = example(
                store,
                cell["cell_id"],
                cell["origin_episode"],
                cell["action_index"],
                program,
                {
                    "source": name,
                    "report": SOURCES[name][2],
                    "candidate_id": cell["candidate_id"],
                    "cell_id": cell["cell_id"],
                    "cell_digest": digest(cell),
                    "checkpoint_digest": cell["checkpoint_digest"],
                },
                eligible=cell["eligible"],
                exclusion=cell["exclusion"],
            )
            diagnostic.append(row)
            if name == "c18" and cell["cell_id"] == "c18b-edit-02":
                require(
                    candidate["proposal"]["program_ast_digest"] == TRAIN_AST["c18"]
                    and row["public"]["label"]
                    and cell["eligible"],
                    "registered c18 training repair changed",
                )
                new_training = (row, candidate["origin"])
    require(
        len(diagnostic) == 48 and new_training is not None,
        "complete 48-cell sample required",
    )
    # Both source failures are independently recollected full factual sequences.
    for name, (positive, origin), control in (
        ("c17", retained, "c17b-control-00"),
        ("c18", new_training, "c18b-control-00"),
    ):
        cell = stores[name].read("effect_cells", control)
        require(
            cell["origin_episode"] == positive["origin_episode"], "wrong factual source"
        )
        negative = example(
            stores[name],
            control,
            positive["origin_episode"],
            positive["action_index"],
            origin["step"]["code"],
            {
                "source": name,
                "report": SOURCES[name][2],
                "cell_id": control,
                "cell_digest": digest(cell),
                "note": "original action at training boundary in audited full factual continuation",
            },
        )
        require(
            not negative["public"]["label"], "training negative is not factual failure"
        )
        training.extend([negative, positive])
    return training, diagnostic, audits
