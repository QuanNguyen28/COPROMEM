"""Environment independent acquisition, retrieval, and replay admission.

Adapters own trajectory normalization and execution. This module only consumes
observable operations, slots, task identities, and scorer results.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Protocol, Sequence

from .schema import DecompositionSchema
from .types import DependencyEdge, SubtaskNode


STATE_VERSION = 5


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


def _operation(value: str) -> str:
    # Only spelling and separators are normalized; different verbs remain different.
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _template(value: str, parameters: dict[str, Any]) -> str:
    for slot, concrete in sorted(parameters.items(), key=lambda item: -len(str(item[1]))):
        if concrete is not None and str(concrete):
            value = re.sub(r"(?<!\w)" + re.escape(str(concrete)) + r"(?!\w)",
                           lambda _: "{" + slot + "}", value)
    return value


@dataclass(frozen=True)
class ActionObservation:
    operation: str
    input_slots: tuple[str, ...] = ()
    output_slots: tuple[str, ...] = ()
    precondition: str = ""
    check: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    observed: bool = True


@dataclass(frozen=True)
class ValidationTask:
    task_id: str
    seed: int
    payload: Any = None


@dataclass(frozen=True)
class ReplayOutcome:
    score: float
    cost: float
    artifact_id: str

    def __post_init__(self) -> None:
        if (not math.isfinite(self.score) or not 0 <= self.score <= 1
                or not math.isfinite(self.cost) or self.cost < 0 or not self.artifact_id):
            raise ValueError("replay requires normalized score, nonnegative cost, and artifact ID")


class ReplayEvaluator(Protocol):
    def upper_bound(self, task: ValidationTask, variant: str) -> float: ...
    def evaluate(self, task: ValidationTask, guidance: str, variant: str) -> ReplayOutcome: ...


@dataclass
class LearnedProcedure:
    procedure_id: str
    schema_id: str
    step_id: str
    text: str
    source_task_id: str
    status: str = "pending"
    source_episode_id: str = ""
    replay_artifacts: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Retrieval:
    text: str
    schema_id: str | None = None
    procedure_ids: tuple[str, ...] = ()
    compatibility: str = "unknown"


class LearningCore:
    """Versioned online memory; a scored winner becomes usable on the next task."""

    def __init__(self) -> None:
        self.schemas: dict[str, DecompositionSchema] = {}
        self.procedures: dict[str, LearnedProcedure] = {}
        self.episodes: dict[str, str] = {}
        self.episode_schemas: dict[str, str] = {}
        self.episode_procedures: dict[str, list[str]] = {}
        self.episode_success: dict[str, bool] = {}
        self.episode_step_evidence: dict[str, list[dict[str, str]]] = {}
        self.pending: dict[str, dict[str, Any]] = {}
        self.admission: dict[str, dict[str, Any]] = {}
        self.feedback: dict[str, dict[str, str]] = {}

    @staticmethod
    def signature(events: Sequence[ActionObservation]) -> dict[str, Any] | None:
        if not events or any(not e.observed or not _operation(e.operation) for e in events):
            return None
        steps = [{"operation": _operation(_template(e.operation, e.parameters)),
                  "inputs": sorted(set(e.input_slots)),
                  "outputs": sorted(set(e.output_slots))} for e in events]
        if any(not (s["inputs"] or s["outputs"]) for s in steps):
            return None
        edges = [[i, i + 1] for i in range(len(steps) - 1)]
        flows = [[i, j, slot] for i, left in enumerate(steps)
                 for j in range(i + 1, len(steps))
                 for slot in set(left["outputs"]) & set(steps[j]["inputs"])]
        return {"steps": steps, "edges": edges, "flows": sorted(flows)}

    def observe(self, episode_id: str, task_id: str, events: Sequence[ActionObservation],
                success: bool, family: str = "general") -> str | None:
        if not episode_id:
            raise ValueError("episode ID is required")
        raw = {"task_id": task_id, "events": [asdict(e) for e in events],
               "success": success, "family": family}
        fingerprint = _digest(raw)
        if episode_id in self.episodes:
            if self.episodes[episode_id] != fingerprint:
                raise ValueError(f"episode ID {episode_id!r} has different content")
            return self.episode_schemas.get(episode_id)
        events = tuple(ActionObservation(
            _template(e.operation, e.parameters), e.input_slots, e.output_slots,
            _template(e.precondition, e.parameters), _template(e.check, e.parameters),
            {}, e.observed) for e in events)
        signature = self.signature(events)
        self.episodes[episode_id] = fingerprint
        self.episode_success[episode_id] = bool(success)
        self.episode_step_evidence[episode_id] = [
            {"precondition": e.precondition, "check": e.check} for e in events]
        self.episode_procedures[episode_id] = []
        if signature is None:
            sid = f"candidate_{_digest([episode_id, fingerprint])[:16]}"
            self.episode_schemas[episode_id] = sid
            self.pending[sid] = {"reason": "insufficient structural evidence",
                                 "episode_ids": [episode_id], "source_task_id": task_id}
            return sid
        sid = f"schema_{_digest([family, signature])[:16]}"
        self.episode_schemas[episode_id] = sid
        if sid not in self.schemas:
            nodes = tuple(SubtaskNode(f"step_{i + 1}", "agent", e.operation,
                                      tuple(sorted(e.input_slots)), tuple(sorted(e.output_slots)))
                          for i, e in enumerate(events))
            edges = tuple(DependencyEdge(nodes[i].node_id, nodes[i + 1].node_id)
                          for i in range(len(nodes) - 1))
            self.schemas[sid] = DecompositionSchema(
                sid, family, (), nodes, edges,
                structural_stats={"signature": signature, "source_task_id": task_id,
                                  "source_task_ids": [task_id],
                                  "step_evidence": []})
        else:
            schema = self.schemas[sid]
            source_ids = set(schema.structural_stats.get("source_task_ids", ()))
            source_ids.add(task_id)
            self.schemas[sid] = schema.with_stats(source_task_ids=sorted(source_ids))
        item = self.pending.setdefault(sid, {"episode_ids": [], "source_task_id": task_id})
        item["episode_ids"].append(episode_id)
        if success:
            for i, event in enumerate(events):
                if not event.check or not event.output_slots:
                    continue
                step_id = f"step_{i + 1}"
                pid = f"procedure_{_digest([sid, step_id, _operation(event.operation), event.check])[:16]}"
                self.procedures.setdefault(pid, LearnedProcedure(
                    pid, sid, step_id,
                    f"Perform {event.operation} using {', '.join(event.input_slots) or 'available inputs'}; "
                    f"verify {event.check} before using {', '.join(event.output_slots)}.", task_id,
                    source_episode_id=episode_id))
                self.episode_procedures[episode_id].append(pid)
        return sid

    def promote_episode(self, episode_id: str) -> bool:
        """Promote only the scored winning episode's structurally grounded memory."""
        sid = self.episode_schemas.get(episode_id)
        pids = self.episode_procedures.get(episode_id, ())
        if not self.episode_success.get(episode_id) or sid not in self.schemas or not pids:
            return False
        schema = self.schemas[sid]
        if schema.status == "quarantined":
            return False
        if schema.status == "candidate":
            self.schemas[sid] = replace(schema, status="provisional")
        self.schemas[sid] = self.schemas[sid].with_stats(
            step_evidence=self.episode_step_evidence[episode_id],
            evidence_episode_id=episode_id)
        for pid in pids:
            proc = self.procedures[pid]
            if proc.status == "pending":
                proc.status = "provisional"
        self.pending.pop(sid, None)
        return True

    def record_feedback(self, schema_id: str | None, task_id: str, seed: int,
                        score: float, no_memory_score: float) -> None:
        """Quarantine after matched harm on two distinct tasks; no causal claim."""
        if schema_id not in self.schemas:
            return
        if not all(math.isfinite(v) and 0 <= v <= 1 for v in (score, no_memory_score)):
            raise ValueError("feedback scores must be normalized")
        by_task = self.feedback.setdefault(schema_id, {})
        outcome = "harm" if score < no_memory_score else ("gain" if score > no_memory_score else "tie")
        by_task[f"{task_id}:{seed}"] = outcome
        harmed_tasks = {key.rsplit(":", 1)[0] for key, value in by_task.items() if value == "harm"}
        if len(harmed_tasks) >= 2:
            self.schemas[schema_id] = replace(self.schemas[schema_id], status="quarantined")

    def retrieve(self, family: str, events: Sequence[ActionObservation] | None = None) -> Retrieval:
        signature = self.signature(events or ())
        if signature is None:
            # An incompatible descriptor is not learned memory.  Returning
            # generic advice here makes the memory arm differ from No Memory
            # while providing no provenance-bound procedure, and it can be
            # mistaken for retrieval in aggregate reporting.  Keep the
            # structural classification, but inject no text.
            return Retrieval("", compatibility="unknown")
        sid = f"schema_{_digest([family, signature])[:16]}"
        schema = self.schemas.get(sid)
        if schema is None or schema.status not in {"provisional", "admitted"}:
            return Retrieval("",
                             compatibility="conflict" if schema is not None and schema.status == "quarantined"
                             else "unknown")
        lines = [f"# Admitted workflow ({sid})"]
        pids = []
        for node in schema.topological_sort():
            lines.append(f"- {node.node_id}: {node.intent}; inputs: {', '.join(node.input_keys) or 'none'}; "
                         f"outputs: {', '.join(node.output_keys) or 'none'}.")
            evidence = (schema.structural_stats.get("step_evidence", []) + [{}] * len(schema.nodes))[
                int(node.node_id.split("_")[-1]) - 1]
            if evidence.get("precondition"):
                lines.append(f"  Before: {evidence['precondition']}")
            if evidence.get("check"):
                lines.append(f"  Verify: {evidence['check']}")
            for proc in self.procedures.values():
                if proc.schema_id == sid and proc.step_id == node.node_id and proc.status in {"provisional", "admitted"}:
                    lines.append(f"  Check: {proc.text}")
                    pids.append(proc.procedure_id)
        return Retrieval("\n".join(lines), sid, tuple(pids), "compatible")

    def validate(self, schema_id: str, tasks: Sequence[ValidationTask],
                 evaluator: ReplayEvaluator | None, budget: float) -> bool:
        """Optional offline diagnostic; it never changes online usability."""
        schema = self.schemas.get(schema_id)
        if schema is None or evaluator is None or budget <= 0:
            return False
        sources = set(schema.structural_stats.get("source_task_ids", [schema.structural_stats["source_task_id"]]))
        independent_by_id: dict[str, ValidationTask] = {}
        for task in tasks:
            if task.task_id not in sources:
                independent_by_id.setdefault(task.task_id, task)
        independent = list(independent_by_id.values())
        if len(independent) < 2:
            return False
        independent = independent[:2]
        proc_ids = [p.procedure_id for p in self.procedures.values() if p.schema_id == schema_id]
        schema_text = self._render_schema(schema)
        full_text = self._render_schema(schema, [self.procedures[pid] for pid in proc_ids])
        outcomes: list[dict[str, ReplayOutcome]] = []
        spent = 0.0
        for task in independent:
            row = {}
            for variant, guidance in (("no_memory", ""), ("schema", schema_text),
                                      ("schema_procedure", full_text)):
                upper_bound = evaluator.upper_bound(task, variant)
                if (not math.isfinite(upper_bound) or upper_bound < 0
                        or spent + upper_bound > budget):
                    return False
                result = evaluator.evaluate(task, guidance, variant)
                spent += result.cost
                if result.cost > upper_bound or spent > budget:
                    raise ValueError("replay evaluator exceeded its declared cost bound")
                row[variant] = result
            outcomes.append(row)
        schema_gains = [r["schema"].score - r["no_memory"].score for r in outcomes]
        procedure_gains = [r["schema_procedure"].score - r["schema"].score for r in outcomes]
        schema_ok = min(schema_gains) >= 0 and max(schema_gains) > 0
        procedure_ok = bool(proc_ids) and schema_ok and min(procedure_gains) >= 0 and max(procedure_gains) > 0
        artifacts = [{v: asdict(result) for v, result in row.items()} for row in outcomes]
        self.admission[schema_id] = {"tasks": [asdict(t) for t in independent],
                                     "outcomes": artifacts, "cost": spent,
                                     "schema_admitted": schema_ok,
                                     "procedure_admitted": procedure_ok}
        return schema_ok

    @staticmethod
    def _render_schema(schema: DecompositionSchema,
                       procedures: Sequence[LearnedProcedure] = ()) -> str:
        lines = [f"Workflow {schema.schema_id}:"]
        for node in schema.topological_sort():
            lines.append(f"{node.node_id}: {node.intent}; input {', '.join(node.input_keys)}; "
                         f"output {', '.join(node.output_keys)}")
            evidence = (schema.structural_stats.get("step_evidence", []) + [{}] * len(schema.nodes))[
                int(node.node_id.split("_")[-1]) - 1]
            if evidence.get("precondition"):
                lines.append(f"  Before: {evidence['precondition']}")
            if evidence.get("check"):
                lines.append(f"  Verify: {evidence['check']}")
            for proc in procedures:
                if proc.step_id == node.node_id:
                    lines.append(f"  Check: {proc.text}")
        return "\n".join(lines)

    def export_state(self) -> dict[str, Any]:
        return {"version": STATE_VERSION,
                "schemas": [s.as_dict() for s in self.schemas.values()],
                "procedures": [asdict(p) for p in self.procedures.values()],
                "episodes": self.episodes, "episode_schemas": self.episode_schemas,
                "episode_procedures": self.episode_procedures,
                "episode_success": self.episode_success,
                "episode_step_evidence": self.episode_step_evidence,
                "feedback": self.feedback,
                "pending": self.pending, "admission": self.admission}

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> LearningCore:
        if state.get("version") != STATE_VERSION:
            raise ValueError("legacy CoProMem state is audit-only; start a version 5 state")
        core = cls()
        core.schemas = {s["schema_id"]: DecompositionSchema.from_dict(s) for s in state["schemas"]}
        core.procedures = {p["procedure_id"]: LearnedProcedure(**p) for p in state["procedures"]}
        core.episodes = dict(state["episodes"])
        core.episode_schemas = dict(state["episode_schemas"])
        core.episode_procedures = {key: list(value) for key, value in state["episode_procedures"].items()}
        core.episode_success = dict(state["episode_success"])
        core.episode_step_evidence = {key: list(value) for key, value in state["episode_step_evidence"].items()}
        core.feedback = {key: dict(value) for key, value in state["feedback"].items()}
        core.pending = dict(state["pending"])
        core.admission = dict(state["admission"])
        return core
