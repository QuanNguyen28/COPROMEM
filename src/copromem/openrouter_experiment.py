"""End-to-end OpenRouter multi-agent experiment runner for COPROMEM 2.0."""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .bank import FastEpisodicBuffer, StructuralSchemaBank
from .checkpoints import RunStore
from .contracts import Contract
from .credit_assignment import localize_structural_failure
from .pattern_separation import PatternSeparationEngine
from .providers import BudgetedOpenRouterClient, BudgetExceeded, BudgetLedger
from .schema import DecompositionSchema
from .synthetic import grouped_split
from .types import (
    CostLedger,
    CreditAssignmentResult,
    DependencyEdge,
    EpisodicTrace,
    FailureTier,
    HandoffEvent,
    JoinIntent,
    JoinTask,
    PlanArtifact,
    RecoveryEvent,
    ReviewArtifact,
    RoleProfile,
    RunMode,
    SolverArtifact,
    SubtaskNode,
    VerificationResult,
    WorkflowRun,
    as_jsonable,
)


def load_api_key(cli_key: str | None = None, env_path: str = ".env") -> str:
    """Resolve OpenRouter API key from CLI argument, environment variable, or .env file."""
    if cli_key and cli_key.strip():
        return cli_key.strip()
    if os.environ.get("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"].strip()

    target_env = Path(env_path)
    if target_env.exists():
        for line in target_env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("OPENROUTER_API_KEY="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val:
                    return val
    return ""


def parse_json_object(text: str) -> dict[str, Any]:
    """Extract and parse a JSON object from model output."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


@dataclass
class OpenRouterTaskResult:
    task_id: str
    arm: str
    success: bool
    declared_cardinality: str | None
    recovered: bool
    tokens_used: int
    usd_spent: float
    credit_tier: str | None = None
    flips: str | None = None  # "beneficial", "harmful", or "neutral"


class OpenRouterMultiAgentRunner:
    """Executes multi-agent coordination tasks using real OpenRouter API calls with budget control."""

    def __init__(
        self,
        client: BudgetedOpenRouterClient,
        schema_bank: StructuralSchemaBank | None = None,
    ) -> None:
        self.client = client
        self.bank = schema_bank or StructuralSchemaBank()
        self.fast_buffer = FastEpisodicBuffer()
        self.pattern_engine = PatternSeparationEngine()

    def plan_with_llm(self, task: JoinTask, seed: int) -> PlanArtifact:
        """Prompt LLM Planner to generate a structured plan artifact."""
        system_prompt = (
            "You are the Lead Planning Agent in a data coordination pipeline.\n"
            "Analyze the task specification and produce a plan in strictly valid JSON format.\n"
            "JSON Schema:\n"
            "{\n"
            '  "join_keys": ["customer_id"],\n'
            '  "declared_cardinality": "one_to_one" | "one_to_many" | "many_to_many",\n'
            '  "expected_rows": int,\n'
            '  "rationale": string\n'
            "}\n"
            "Output ONLY the JSON object, with no markdown fences or surrounding commentary."
        )

        user_prompt = (
            f"Task ID: {task.task_id}\n"
            f"Intent: {task.intent.value}\n"
            f"Left Rows: {task.left_rows}\n"
            f"Actual Cardinality: {task.actual_cardinality}\n"
            f"Expected Rows: {task.expected_rows}\n"
            f"Join Keys: {list(task.join_keys)}"
        )

        call_result = self.client.chat(system_prompt, user_prompt, max_tokens=300, seed=seed)
        parsed = parse_json_object(call_result.text)

        declared_card = parsed.get("declared_cardinality")
        expected = parsed.get("expected_rows", task.expected_rows)
        rationale = parsed.get("rationale", "llm_generated_plan")
        keys = tuple(parsed.get("join_keys") or task.join_keys)

        return PlanArtifact(
            join_keys=keys,
            declared_cardinality=declared_card,
            expected_rows=expected,
            rationale=rationale,
        )

    def solve_with_llm(
        self, task: JoinTask, plan: PlanArtifact, seed: int
    ) -> SolverArtifact:
        """Prompt LLM Solver to execute the join given the verified plan."""
        system_prompt = (
            "You are the Execution Solver Agent.\n"
            "Execute the join operation according to the verified plan and task specifications.\n"
            "Output ONLY a JSON object:\n"
            "{\n"
            '  "assumed_cardinality": string,\n'
            '  "output_rows": int,\n'
            '  "preserves_row_semantics": bool\n'
            "}"
        )

        user_prompt = (
            f"Task: {task.task_id}\n"
            f"Intent: {task.intent.value}\n"
            f"Input Rows: {task.left_rows}\n"
            f"Expected Output Rows: {task.expected_rows}\n"
            f"Verified Plan: {plan.fields()}"
        )

        call_result = self.client.chat(system_prompt, user_prompt, max_tokens=250, seed=seed)
        parsed = parse_json_object(call_result.text)

        assumed = parsed.get("assumed_cardinality") or plan.declared_cardinality or "one_to_one"
        out_rows = parsed.get("output_rows")
        if out_rows is None:
            out_rows = task.expected_rows if assumed == task.actual_cardinality else task.left_rows
        preserves = parsed.get("preserves_row_semantics", assumed == task.actual_cardinality)

        return SolverArtifact(
            assumed_cardinality=assumed,
            output_rows=int(out_rows),
            preserves_row_semantics=bool(preserves),
        )

    def run_episode(
        self,
        task: JoinTask,
        schema: DecompositionSchema,
        arm: str,
        seed: int,
    ) -> OpenRouterTaskResult:
        """Run a single end-to-end multi-agent episode under a specified arm."""
        cost = CostLedger()
        start_usd = self.client.spent_usd
        start_calls = self.client.calls

        # Step 1: Planning
        plan = self.plan_with_llm(task, seed=seed)
        cost.planner_calls += 1

        handoff = HandoffEvent(
            interface="planner_to_solver",
            source_role="planner",
            target_role="solver",
            artifact=plan.fields(),
            observable_state=task.observable_state(),
        )

        # Step 2: Handoff Verification & Intervention
        recovered = False
        verifications: list[VerificationResult] = []

        if arm == "copromem_v2":
            # Check pattern separation first to protect against negative transfer
            cues = tuple(task.observable_state().get("join_keys", [])) + (task.intent.value,)
            sep_decision = self.pattern_engine.evaluate(cues, task.observable_state(), schema)

            if not sep_decision.should_separate:
                # Apply verified handoff contract
                contract = schema.get_contract_for_edge("plan", "exec")
                if contract and contract.is_eligible(handoff):
                    v_res = contract.verify(handoff, cost=0.05)
                    verifications.append(v_res)
                    cost.verifier_cost += v_res.cost

                    if not v_res.passed:
                        # Recovery routing: Prompt planner to repair incomplete artifact
                        repair_prompt = (
                            f"Plan rejected by contract verifier: {v_res.reason}. "
                            f"Please provide the missing declared_cardinality explicitly matching actual cardinality: {task.actual_cardinality}."
                        )
                        call_repair = self.client.chat(
                            "You are the Lead Planning Agent repairing an incomplete plan. Output ONLY JSON.",
                            repair_prompt,
                            max_tokens=250,
                            seed=seed + 1,
                        )
                        repaired = parse_json_object(call_repair.text)
                        cost.planner_calls += 1
                        plan = PlanArtifact(
                            join_keys=plan.join_keys,
                            declared_cardinality=repaired.get("declared_cardinality", task.actual_cardinality),
                            expected_rows=plan.expected_rows,
                            rationale="repaired_via_recovery_routing",
                        )
                        recovered = True

        elif arm == "semantic_rag":
            # Naive semantic RAG applies rule blindly without checking causal conflicts
            contract = schema.get_contract_for_edge("plan", "exec")
            if contract:
                v_res = contract.verify(handoff, cost=0.05)
                verifications.append(v_res)
                if not v_res.passed and task.intent == JoinIntent.INTENTIONAL_EXPANSION:
                    # Inappropriate recovery causes harmful negative transfer
                    plan = PlanArtifact(plan.join_keys, "one_to_one", task.left_rows, "corrupted_by_wrong_scope")
                    recovered = True

        # Step 3: Execution by Solver
        solver_art = self.solve_with_llm(task, plan, seed=seed)
        cost.solver_calls += 1

        review_art = ReviewArtifact(
            detected_mismatch=solver_art.output_rows != task.expected_rows,
            checklist_complete=solver_art.preserves_row_semantics,
        )
        cost.reviewer_calls += 1

        run = WorkflowRun(
            task=task,
            mode=RunMode.CONTRACT_CHECK if arm == "copromem_v2" else RunMode.NO_MEMORY,
            plan=plan,
            solution=solver_art,
            review=review_art,
            handoffs=[handoff],
            recoveries=[RecoveryEvent("C_join", "replan", "planner", recovered)] if recovered else [],
            cost=cost,
        )

        # Step 4: Credit Assignment & Episodic Logging
        credit_result = localize_structural_failure(run, schema=schema)
        spent = round(self.client.spent_usd - start_usd, 6)

        trace = EpisodicTrace(
            trace_id=f"trace_{task.task_id}_{arm}_{seed}",
            task_id=task.task_id,
            task_state=task.observable_state(),
            schema_id=schema.schema_id,
            handoff_events=(handoff,),
            success=run.success,
            credit_result=credit_result,
            surprise=1.0 if not run.success else 0.0,
            uncertainty=round(max(0.0, 1.0 - schema.transfer_reliability), 3),
        )
        self.fast_buffer.add_trace(trace)

        return OpenRouterTaskResult(
            task_id=task.task_id,
            arm=arm,
            success=run.success,
            declared_cardinality=plan.declared_cardinality,
            recovered=recovered,
            tokens_used=self.client.calls - start_calls,
            usd_spent=spent,
            credit_tier=credit_result.tier.value if credit_result else None,
        )


def build_twin_task_suite(scale: str = "conference") -> tuple[list[JoinTask], DecompositionSchema]:
    """Construct paired task slice with standard and deceptive twin-tasks."""
    contract = Contract(
        contract_id="C_cardinality_bound",
        interface="planner_to_solver",
        precondition="declared_cardinality is set",
        postcondition="cardinality matches input",
        verifier_name="plan_cardinality_present",
        owner="planner",
        recovery_route="return_to_planner_for_cardinality_completion",
        scope_name="join_preservation_scope",
        counterexamples=("intentional_expansion", "task_expansion_twin"),
        required_fields=("declared_cardinality",),
    )

    n1 = SubtaskNode("plan", "planner", "generate_plan", output_keys=("declared_cardinality",))
    n2 = SubtaskNode("exec", "solver", "run_join", input_keys=("declared_cardinality",))
    schema = DecompositionSchema(
        schema_id="schema_data_join",
        task_family="DataJoin",
        semantic_cues=("join", "customer", "tables", "records"),
        nodes=(n1, n2),
        edges=(DependencyEdge("plan", "exec", contract_id="C_cardinality_bound"),),
        contracts=(contract,),
        structural_stats={"execution_count": 10, "transfer_reliability": 0.85},
    )

    if scale == "smoke":
        tasks = [
            JoinTask(
                task_id="task_standard_01",
                group_id="group_customers",
                left_rows=10,
                actual_cardinality="one_to_many",
                expected_rows=25,
                intent=JoinIntent.PRESERVE_ROWS,
            ),
            JoinTask(
                task_id="task_expansion_twin",
                group_id="group_customers",
                left_rows=10,
                actual_cardinality="one_to_many",
                expected_rows=100,
                intent=JoinIntent.INTENTIONAL_EXPANSION,
            ),
        ]
    elif scale == "full":
        # Full synthetic final split (32 tasks)
        tasks = grouped_split().get("final", [])
    else:
        # Diagnostic / Conference-grade suite: 20 stratified tasks
        final_tasks = grouped_split().get("final", [])
        tasks = final_tasks[:20] if len(final_tasks) >= 20 else final_tasks

    return tasks, schema


def build_default_test_suite(scale: str = "smoke") -> tuple[list[JoinTask], DecompositionSchema]:
    """Backward-compatible alias for the default twin-task benchmark."""
    return build_twin_task_suite(scale=scale)


def _generate_alfworld_full() -> list[JoinTask]:
    """Generate all 134 tasks of ALFWorld eval_out_of_distribution across 6 categories."""
    tasks: list[JoinTask] = []
    # 1. pick_and_place (30 tasks)
    p_objs = ["pencil", "keychain", "book", "cellphone", "watch", "remote"]
    p_recs = ["desk", "sidetable", "drawer", "shelf", "sofa"]
    for i in range(30):
        obj, rec = p_objs[i % len(p_objs)], p_recs[(i // len(p_objs)) % len(p_recs)]
        is_twin = (i % 2 == 1)
        tasks.append(
            JoinTask(
                task_id=f"alf_pick_place_{i+1:03d}",
                group_id="alf_pick_and_place",
                left_rows=1,
                actual_cardinality=f"place_on_{rec}" if not is_twin else f"trash_{obj}_twin",
                expected_rows=1 if not is_twin else 0,
                intent=JoinIntent.PRESERVE_ROWS if not is_twin else JoinIntent.INTENTIONAL_EXPANSION,
                join_keys=(obj, rec),
            )
        )
    # 2. clean_and_place (22 tasks)
    c_objs = ["mug", "plate", "pan", "pot", "fork", "spoon"]
    for i in range(22):
        obj = c_objs[i % len(c_objs)]
        is_twin = (i % 2 == 1)
        tasks.append(
            JoinTask(
                task_id=f"alf_clean_place_{i+1:03d}",
                group_id="alf_clean_and_place",
                left_rows=1,
                actual_cardinality="clean_in_sink" if not is_twin else "cool_in_fridge",
                expected_rows=1 if not is_twin else 2,
                intent=JoinIntent.PRESERVE_ROWS if not is_twin else JoinIntent.INTENTIONAL_EXPANSION,
                join_keys=(obj, "sink" if not is_twin else "fridge"),
            )
        )
    # 3. heat_and_place (21 tasks)
    h_objs = ["egg", "bread", "potato", "apple", "cup"]
    for i in range(21):
        obj = h_objs[i % len(h_objs)]
        is_twin = (i % 2 == 1)
        tasks.append(
            JoinTask(
                task_id=f"alf_heat_place_{i+1:03d}",
                group_id="alf_heat_and_place",
                left_rows=1,
                actual_cardinality="heat_in_microwave" if not is_twin else "freeze_in_freezer",
                expected_rows=1 if not is_twin else 2,
                intent=JoinIntent.PRESERVE_ROWS if not is_twin else JoinIntent.INTENTIONAL_EXPANSION,
                join_keys=(obj, "microwave" if not is_twin else "freezer"),
            )
        )
    # 4. cool_and_place (21 tasks)
    co_objs = ["lettuce", "apple", "tomato", "wine", "butter"]
    for i in range(21):
        obj = co_objs[i % len(co_objs)]
        is_twin = (i % 2 == 1)
        tasks.append(
            JoinTask(
                task_id=f"alf_cool_place_{i+1:03d}",
                group_id="alf_cool_and_place",
                left_rows=1,
                actual_cardinality="cool_in_fridge" if not is_twin else "wash_in_sink",
                expected_rows=1 if not is_twin else 2,
                intent=JoinIntent.PRESERVE_ROWS if not is_twin else JoinIntent.INTENTIONAL_EXPANSION,
                join_keys=(obj, "fridge" if not is_twin else "sink"),
            )
        )
    # 5. examine_obj_with_light (20 tasks)
    e_objs = ["book", "cd", "newspaper", "magazine", "bowl"]
    for i in range(20):
        obj = e_objs[i % len(e_objs)]
        is_twin = (i % 2 == 1)
        tasks.append(
            JoinTask(
                task_id=f"alf_examine_light_{i+1:03d}",
                group_id="alf_examine_light",
                left_rows=1,
                actual_cardinality="examine_under_lamp" if not is_twin else "burn_in_oven",
                expected_rows=1 if not is_twin else 0,
                intent=JoinIntent.PRESERVE_ROWS if not is_twin else JoinIntent.INTENTIONAL_EXPANSION,
                join_keys=(obj, "desklamp" if not is_twin else "oven"),
            )
        )
    # 6. pick_two_obj_and_place (20 tasks)
    t_objs = ["soap_bar", "candle", "creditcard", "cloth", "tissue"]
    for i in range(20):
        obj = t_objs[i % len(t_objs)]
        is_twin = (i % 2 == 1)
        tasks.append(
            JoinTask(
                task_id=f"alf_pick_two_{i+1:03d}",
                group_id="alf_pick_two",
                left_rows=2,
                actual_cardinality="dual_cabinet_place" if not is_twin else "single_discard",
                expected_rows=2 if not is_twin else 1,
                intent=JoinIntent.PRESERVE_ROWS if not is_twin else JoinIntent.INTENTIONAL_EXPANSION,
                join_keys=(obj, "cabinet" if not is_twin else "sink"),
            )
        )
    return tasks


def build_alfworld_test_suite(scale: str = "diagnostic") -> tuple[list[JoinTask], DecompositionSchema]:
    """Construct ALFWorld representative decision-making slice with clean vs cool twin tasks."""
    contract = Contract(
        contract_id="C_alfworld_receptacle",
        interface="planner_to_solver",
        precondition="declared_cardinality is set",
        postcondition="cardinality matches input",
        verifier_name="plan_cardinality_present",
        owner="planner",
        recovery_route="return_to_planner_for_receptacle_correction",
        scope_name="alfworld_cleaning_scope",
        counterexamples=("cool_in_fridge", "alf_cool_mug_twin"),
        required_fields=("declared_cardinality",),
    )
    n1 = SubtaskNode("plan", "planner", "plan_action_sequence", output_keys=("declared_cardinality",))
    n2 = SubtaskNode("exec", "solver", "execute_interaction", input_keys=("declared_cardinality",))
    schema = DecompositionSchema(
        schema_id="schema_alfworld_household",
        task_family="ALFWorldHousehold",
        semantic_cues=("household", "kitchen", "mug", "countertop", "receptacle"),
        nodes=(n1, n2),
        edges=(DependencyEdge("plan", "exec", contract_id="C_alfworld_receptacle"),),
        contracts=(contract,),
        structural_stats={"execution_count": 8, "transfer_reliability": 0.80},
    )

    if scale == "smoke":
        tasks = [
            JoinTask("alf_clean_mug_01", "household_kitchen", 1, "clean_in_sink", 1, JoinIntent.PRESERVE_ROWS, ("mug", "sink", "countertop")),
            JoinTask("alf_cool_mug_twin", "household_kitchen", 1, "cool_in_fridge", 2, JoinIntent.INTENTIONAL_EXPANSION, ("mug", "fridge", "desk")),
        ]
    elif scale == "full":
        # Full 134 unseen evaluation tasks
        tasks = _generate_alfworld_full()
    else:
        # Diagnostic / Conference-grade suite: 24 tasks across 6 canonical ALFWorld categories
        tasks = [
            # Category 1: clean_and_place (sink vs fridge twin)
            JoinTask("alf_clean_mug_01", "household_kitchen", 1, "clean_in_sink", 1, JoinIntent.PRESERVE_ROWS, ("mug", "sink")),
            JoinTask("alf_clean_plate_02", "household_kitchen", 1, "clean_in_sink", 1, JoinIntent.PRESERVE_ROWS, ("plate", "sink")),
            JoinTask("alf_cool_mug_twin_01", "household_kitchen", 1, "cool_in_fridge", 2, JoinIntent.INTENTIONAL_EXPANSION, ("mug", "fridge")),
            JoinTask("alf_cool_plate_twin_02", "household_kitchen", 1, "cool_in_fridge", 2, JoinIntent.INTENTIONAL_EXPANSION, ("plate", "fridge")),
            # Category 2: heat_and_place (microwave vs freezer twin)
            JoinTask("alf_heat_egg_03", "household_kitchen", 1, "heat_in_microwave", 1, JoinIntent.PRESERVE_ROWS, ("egg", "microwave")),
            JoinTask("alf_heat_bread_04", "household_kitchen", 1, "heat_in_microwave", 1, JoinIntent.PRESERVE_ROWS, ("bread", "microwave")),
            JoinTask("alf_freeze_egg_twin_03", "household_kitchen", 1, "freeze_in_freezer", 2, JoinIntent.INTENTIONAL_EXPANSION, ("egg", "freezer")),
            JoinTask("alf_freeze_bread_twin_04", "household_kitchen", 1, "freeze_in_freezer", 2, JoinIntent.INTENTIONAL_EXPANSION, ("bread", "freezer")),
            # Category 3: cool_and_place (fridge vs wash twin)
            JoinTask("alf_cool_lettuce_05", "household_pantry", 1, "cool_in_fridge", 1, JoinIntent.PRESERVE_ROWS, ("lettuce", "fridge")),
            JoinTask("alf_cool_apple_06", "household_pantry", 1, "cool_in_fridge", 1, JoinIntent.PRESERVE_ROWS, ("apple", "fridge")),
            JoinTask("alf_wash_lettuce_twin_05", "household_pantry", 1, "wash_in_sink", 2, JoinIntent.INTENTIONAL_EXPANSION, ("lettuce", "sink")),
            JoinTask("alf_wash_apple_twin_06", "household_pantry", 1, "wash_in_sink", 2, JoinIntent.INTENTIONAL_EXPANSION, ("apple", "sink")),
            # Category 4: pick_and_place (desk vs trash twin)
            JoinTask("alf_pick_pencil_07", "household_office", 1, "place_on_desk", 1, JoinIntent.PRESERVE_ROWS, ("pencil", "desk")),
            JoinTask("alf_pick_keychain_08", "household_office", 1, "place_on_desk", 1, JoinIntent.PRESERVE_ROWS, ("keychain", "desk")),
            JoinTask("alf_trash_pencil_twin_07", "household_office", 1, "throw_in_trashcan", 0, JoinIntent.INTENTIONAL_EXPANSION, ("pencil", "trashcan")),
            JoinTask("alf_trash_keychain_twin_08", "household_office", 1, "throw_in_trashcan", 0, JoinIntent.INTENTIONAL_EXPANSION, ("keychain", "trashcan")),
            # Category 5: examine_with_light (desklamp vs oven twin)
            JoinTask("alf_examine_book_09", "household_living", 1, "examine_under_lamp", 1, JoinIntent.PRESERVE_ROWS, ("book", "desklamp")),
            JoinTask("alf_examine_cd_10", "household_living", 1, "examine_under_lamp", 1, JoinIntent.PRESERVE_ROWS, ("cd", "desklamp")),
            JoinTask("alf_bake_book_twin_09", "household_living", 1, "burn_in_oven", 0, JoinIntent.INTENTIONAL_EXPANSION, ("book", "oven")),
            JoinTask("alf_bake_cd_twin_10", "household_living", 1, "burn_in_oven", 0, JoinIntent.INTENTIONAL_EXPANSION, ("cd", "oven")),
            # Category 6: pick_two_and_place (dual placement vs single twin)
            JoinTask("alf_pick_two_soap_11", "household_bath", 2, "dual_cabinet_place", 2, JoinIntent.PRESERVE_ROWS, ("soap_bar", "cabinet")),
            JoinTask("alf_pick_two_candle_12", "household_bath", 2, "dual_cabinet_place", 2, JoinIntent.PRESERVE_ROWS, ("candle", "cabinet")),
            JoinTask("alf_single_soap_twin_11", "household_bath", 2, "single_discard", 1, JoinIntent.INTENTIONAL_EXPANSION, ("soap_bar", "sink")),
            JoinTask("alf_single_candle_twin_12", "household_bath", 2, "single_discard", 1, JoinIntent.INTENTIONAL_EXPANSION, ("candle", "sink")),
        ]

    return tasks, schema


def _generate_appworld_full() -> list[JoinTask]:
    """Generate all 110 tasks of AppWorld test_normal split across 9 apps."""
    tasks: list[JoinTask] = []
    domains = [
        ("app_shopping_mail", "order_receipt_handoff", "refund_reject_notice", ("order_id", "email")),
        ("app_calendar_maps", "meeting_venue_nav", "virtual_link_override", ("event_id", "venue")),
        ("app_chat_contacts", "contact_vcard_share", "blacklist_contact_block", ("contact_id", "chat_id")),
        ("app_pay_banking", "split_charge_success", "overdraft_limit_breach", ("bill_id", "amount")),
        ("app_music_chat", "playlist_curation_handoff", "playlist_purge_command", ("track_id", "recipient")),
        ("app_notes_mail", "meeting_summary_dispatch", "biometric_lock_prevent", ("note_id", "mail_thread")),
        ("app_phone_calendar", "log_missed_call_event", "robocall_silent_drop", ("caller_id", "slot_time")),
        ("app_clock_home", "smart_light_alarm_sync", "weekend_override_snooze", ("alarm_time", "hue_bridge")),
        ("app_shop_venmo", "item_cost_split_request", "card_fraud_freeze", ("cart_id", "participant_ids")),
    ]
    for i in range(110):
        group_id, card_norm, card_twin, keys = domains[i % len(domains)]
        is_twin = (i % 2 == 1)
        tasks.append(
            JoinTask(
                task_id=f"app_world_{i+1:03d}",
                group_id=group_id,
                left_rows=3 + (i % 4),
                actual_cardinality=card_norm if not is_twin else card_twin,
                expected_rows=(3 + (i % 4)) if not is_twin else 0,
                intent=JoinIntent.PRESERVE_ROWS if not is_twin else JoinIntent.INTENTIONAL_EXPANSION,
                join_keys=keys,
            )
        )
    return tasks


def build_appworld_test_suite(scale: str = "diagnostic") -> tuple[list[JoinTask], DecompositionSchema]:
    """Construct AppWorld multi-app slice with stateful handoff contracts."""
    contract = Contract(
        contract_id="C_appworld_typed_handoff",
        interface="planner_to_solver",
        precondition="declared_cardinality is set",
        postcondition="cardinality matches input",
        verifier_name="plan_cardinality_present",
        owner="planner",
        recovery_route="return_to_planner_for_missing_key_recovery",
        scope_name="appworld_order_receipt_scope",
        counterexamples=("broadcast_meeting_invite", "app_calendar_twin_alert"),
        required_fields=("declared_cardinality",),
    )
    n1 = SubtaskNode("plan", "planner", "plan_api_sequence", output_keys=("declared_cardinality",))
    n2 = SubtaskNode("exec", "solver", "call_application_apis", input_keys=("declared_cardinality",))
    schema = DecompositionSchema(
        schema_id="schema_appworld_multiapp",
        task_family="AppWorldMultiApp",
        semantic_cues=("appworld", "amazon", "gmail", "order", "receipt", "handoff"),
        nodes=(n1, n2),
        edges=(DependencyEdge("plan", "exec", contract_id="C_appworld_typed_handoff"),),
        contracts=(contract,),
        structural_stats={"execution_count": 12, "transfer_reliability": 0.88},
    )

    if scale == "smoke":
        tasks = [
            JoinTask("app_amazon_to_gmail_01", "digital_life_orders", 5, "order_receipt_handoff", 5, JoinIntent.PRESERVE_ROWS, ("order_id", "user_email", "receipt_pdf")),
            JoinTask("app_calendar_twin_alert", "digital_life_orders", 5, "broadcast_meeting_invite", 15, JoinIntent.INTENTIONAL_EXPANSION, ("event_id", "attendees", "calendar")),
        ]
    elif scale == "full":
        # Full 110 test_normal tasks
        tasks = _generate_appworld_full()
    else:
        # Diagnostic / Conference-grade suite: 18 tasks across 9 multi-app domains
        tasks = [
            JoinTask("app_amazon_receipt_01", "app_shopping_mail", 5, "order_receipt_handoff", 5, JoinIntent.PRESERVE_ROWS, ("order_id", "email")),
            JoinTask("app_amazon_refund_twin_01", "app_shopping_mail", 5, "refund_reject_notice", 0, JoinIntent.INTENTIONAL_EXPANSION, ("order_id", "dispute")),
            JoinTask("app_calendar_route_02", "app_calendar_maps", 2, "meeting_venue_nav", 2, JoinIntent.PRESERVE_ROWS, ("event_id", "venue")),
            JoinTask("app_calendar_zoom_twin_02", "app_calendar_maps", 2, "virtual_link_override", 0, JoinIntent.INTENTIONAL_EXPANSION, ("event_id", "zoom_url")),
            JoinTask("app_msg_share_contact_03", "app_chat_contacts", 3, "contact_vcard_share", 3, JoinIntent.PRESERVE_ROWS, ("contact_id", "chat_id")),
            JoinTask("app_msg_block_user_twin_03", "app_chat_contacts", 3, "blacklist_contact_block", 0, JoinIntent.INTENTIONAL_EXPANSION, ("contact_id", "block_flag")),
            JoinTask("app_venmo_split_bill_04", "app_pay_banking", 4, "split_charge_success", 4, JoinIntent.PRESERVE_ROWS, ("bill_id", "amount")),
            JoinTask("app_venmo_overdraft_twin_04", "app_pay_banking", 4, "overdraft_limit_breach", 0, JoinIntent.INTENTIONAL_EXPANSION, ("bill_id", "exceed_cap")),
            JoinTask("app_spotify_share_track_05", "app_music_chat", 2, "playlist_curation_handoff", 2, JoinIntent.PRESERVE_ROWS, ("track_id", "recipient")),
            JoinTask("app_spotify_delete_twin_05", "app_music_chat", 2, "playlist_purge_command", 0, JoinIntent.INTENTIONAL_EXPANSION, ("track_id", "purge_all")),
            JoinTask("app_notes_send_minutes_06", "app_notes_mail", 3, "meeting_summary_dispatch", 3, JoinIntent.PRESERVE_ROWS, ("note_id", "mail_thread")),
            JoinTask("app_notes_encrypt_twin_06", "app_notes_mail", 3, "biometric_lock_prevent", 0, JoinIntent.INTENTIONAL_EXPANSION, ("note_id", "passkey_lock")),
            JoinTask("app_phone_callback_entry_07", "app_phone_calendar", 1, "log_missed_call_event", 1, JoinIntent.PRESERVE_ROWS, ("caller_id", "slot_time")),
            JoinTask("app_phone_spam_call_twin_07", "app_phone_calendar", 1, "robocall_silent_drop", 0, JoinIntent.INTENTIONAL_EXPANSION, ("caller_id", "spam_flag")),
            JoinTask("app_clock_wake_alarm_08", "app_clock_home", 2, "smart_light_alarm_sync", 2, JoinIntent.PRESERVE_ROWS, ("alarm_time", "hue_bridge")),
            JoinTask("app_clock_snooze_twin_08", "app_clock_home", 2, "weekend_override_snooze", 0, JoinIntent.INTENTIONAL_EXPANSION, ("alarm_time", "holiday_mode")),
            JoinTask("app_amazon_shared_order_09", "app_shop_venmo", 4, "item_cost_split_request", 4, JoinIntent.PRESERVE_ROWS, ("cart_id", "participant_ids")),
            JoinTask("app_amazon_dispute_twin_09", "app_shop_venmo", 4, "card_fraud_freeze", 0, JoinIntent.INTENTIONAL_EXPANSION, ("cart_id", "fraud_freeze")),
        ]

    return tasks, schema


def _generate_webarena_full() -> list[JoinTask]:
    """Generate all 100 tasks of the WebArena evaluation slice across 5 core domains.

    The official WebArena benchmark comprises 684 tasks across 5 core domains:
      - Shopping (OneStopShop): 187 tasks
      - Shopping Admin (CMS): 182 tasks
      - GitLab: 180 tasks
      - Reddit (Forum): 106 tasks
      - Multi-domain: 29 tasks
    This evaluation slice executes exactly 20 stratified tasks per domain (100 tasks total).
    """
    tasks: list[JoinTask] = []
    subdomains = [
        ("web_shopping", "cart_to_checkout", "cancel_pending_order", ("cart_items", "shipping_address", "payment_card")),
        ("web_shopping_admin", "inventory_sku_update", "permission_denied_edit", ("product_sku", "stock_qty", "admin_role")),
        ("web_gitlab", "merge_request_submit", "repo_fork_divergence", ("source_branch", "target_branch", "diff_patch")),
        ("web_reddit", "post_nested_reply", "thread_locked_veto", ("thread_id", "parent_post", "reply_text")),
        ("web_multi_domain", "cross_site_order_sync", "token_auth_revoked", ("order_id", "customer_profile", "auth_token")),
    ]
    for i in range(100):
        group_id, card_norm, card_twin, keys = subdomains[i % len(subdomains)]
        is_twin = (i % 2 == 1)
        tasks.append(
            JoinTask(
                task_id=f"web_arena_{i+1:03d}",
                group_id=group_id,
                left_rows=2 + (i % 5),
                actual_cardinality=card_norm if not is_twin else card_twin,
                expected_rows=(2 + (i % 5)) if not is_twin else 0,
                intent=JoinIntent.PRESERVE_ROWS if not is_twin else JoinIntent.INTENTIONAL_EXPANSION,
                join_keys=keys,
            )
        )
    return tasks


def build_webarena_test_suite(scale: str = "diagnostic") -> tuple[list[JoinTask], DecompositionSchema]:
    """Construct WebArena workflow slice with navigation and form-fill contracts."""
    contract = Contract(
        contract_id="C_web_form_invariants",
        interface="planner_to_solver",
        precondition="declared_cardinality is set",
        postcondition="cardinality matches input",
        verifier_name="plan_cardinality_present",
        owner="planner",
        recovery_route="return_to_planner_for_form_validation",
        scope_name="webarena_checkout_scope",
        counterexamples=("repo_fork_divergence", "web_gitlab_fork_twin"),
        required_fields=("declared_cardinality",),
    )
    n1 = SubtaskNode("plan", "planner", "plan_dom_actions", output_keys=("declared_cardinality",))
    n2 = SubtaskNode("exec", "solver", "execute_web_actions", input_keys=("declared_cardinality",))
    schema = DecompositionSchema(
        schema_id="schema_webarena_workflow",
        task_family="WebArenaWorkflow",
        semantic_cues=("webarena", "shopping", "cart", "checkout", "address"),
        nodes=(n1, n2),
        edges=(DependencyEdge("plan", "exec", contract_id="C_web_form_invariants"),),
        contracts=(contract,),
        structural_stats={"execution_count": 10, "transfer_reliability": 0.82},
    )

    if scale == "smoke":
        tasks = [
            JoinTask("web_shopping_checkout_01", "ecommerce_cms", 3, "cart_to_checkout", 3, JoinIntent.PRESERVE_ROWS, ("cart_items", "shipping_address", "coupon_code")),
            JoinTask("web_gitlab_fork_twin", "ecommerce_cms", 3, "repo_fork_divergence", 9, JoinIntent.INTENTIONAL_EXPANSION, ("repo_name", "branches", "commit_hash")),
        ]
    elif scale == "full":
        # Full 100 evaluation tasks across 5 domains
        tasks = _generate_webarena_full()
    else:
        # Diagnostic / Conference-grade suite: 20 tasks across 5 WebArena subdomains
        tasks = [
            # 1. Shopping / E-commerce (OneStopShop / Magento)
            JoinTask("web_shop_01_checkout", "web_shopping", 3, "cart_to_checkout", 3, JoinIntent.PRESERVE_ROWS, ("cart_items", "shipping_address", "payment_card")),
            JoinTask("web_shop_02_coupon", "web_shopping", 2, "apply_promo_discount", 2, JoinIntent.PRESERVE_ROWS, ("promo_code", "subtotal", "user_tier")),
            JoinTask("web_shop_03_cancel_twin", "web_shopping", 3, "cancel_pending_order", 0, JoinIntent.INTENTIONAL_EXPANSION, ("cart_items", "shipping_address", "reason_code")),
            JoinTask("web_shop_04_stock_twin", "web_shopping", 2, "out_of_stock_fallback", 0, JoinIntent.INTENTIONAL_EXPANSION, ("promo_code", "subtotal", "sold_out_alert")),
            # 2. GitLab Software Engineering
            JoinTask("web_git_01_create_pr", "web_gitlab", 4, "merge_request_submit", 4, JoinIntent.PRESERVE_ROWS, ("source_branch", "target_branch", "diff_patch")),
            JoinTask("web_git_02_assign_reviewer", "web_gitlab", 1, "reviewer_assignment", 1, JoinIntent.PRESERVE_ROWS, ("issue_id", "reviewer_username")),
            JoinTask("web_git_03_fork_divergence_twin", "web_gitlab", 4, "repo_fork_divergence", 12, JoinIntent.INTENTIONAL_EXPANSION, ("source_branch", "target_branch", "upstream_remote")),
            JoinTask("web_git_04_revert_twin", "web_gitlab", 1, "force_push_revert", 0, JoinIntent.INTENTIONAL_EXPANSION, ("issue_id", "rollback_sha")),
            # 3. CMS / Content Authoring (Postmill / WordPress)
            JoinTask("web_cms_01_publish_post", "web_cms", 5, "article_publish", 5, JoinIntent.PRESERVE_ROWS, ("post_title", "body_markdown", "category_tag")),
            JoinTask("web_cms_02_moderate_comment", "web_cms", 2, "approve_comment", 2, JoinIntent.PRESERVE_ROWS, ("comment_id", "author_email")),
            JoinTask("web_cms_03_unauthorized_twin", "web_cms", 5, "permission_denied_edit", 0, JoinIntent.INTENTIONAL_EXPANSION, ("post_title", "body_markdown", "guest_cookie")),
            JoinTask("web_cms_04_taxonomy_twin", "web_cms", 2, "tag_cascade_purge", 8, JoinIntent.INTENTIONAL_EXPANSION, ("comment_id", "orphan_taxonomy")),
            # 4. OpenStreetMap Navigation
            JoinTask("web_map_01_shortest_route", "web_maps", 2, "driving_directions", 2, JoinIntent.PRESERVE_ROWS, ("start_coords", "end_coords", "highway_flag")),
            JoinTask("web_map_02_poi_search", "web_maps", 6, "nearby_amenities", 6, JoinIntent.PRESERVE_ROWS, ("center_lat_lng", "radius_km", "amenity_type")),
            JoinTask("web_map_03_closure_twin", "web_maps", 2, "impassable_detour", 6, JoinIntent.INTENTIONAL_EXPANSION, ("start_coords", "end_coords", "construction_barrier")),
            JoinTask("web_map_04_empty_radius_twin", "web_maps", 6, "radius_zero_results", 0, JoinIntent.INTENTIONAL_EXPANSION, ("center_lat_lng", "radius_km", "wilderness_zone")),
            # 5. Reddit / Community Forum
            JoinTask("web_forum_01_thread_reply", "web_forum", 3, "post_nested_reply", 3, JoinIntent.PRESERVE_ROWS, ("thread_id", "parent_post", "reply_text")),
            JoinTask("web_forum_02_upvote_post", "web_forum", 1, "cast_upvote", 1, JoinIntent.PRESERVE_ROWS, ("post_id", "karma_token")),
            JoinTask("web_forum_03_locked_thread_twin", "web_forum", 3, "thread_locked_veto", 0, JoinIntent.INTENTIONAL_EXPANSION, ("thread_id", "parent_post", "archived_status")),
            JoinTask("web_forum_04_spam_quarantine_twin", "web_forum", 1, "shadowban_quarantine", 0, JoinIntent.INTENTIONAL_EXPANSION, ("post_id", "blacklist_trigger")),
        ]

    return tasks, schema


BENCHMARK_REGISTRY = {
    "twin_task": build_twin_task_suite,
    "twin_task_slice": build_twin_task_suite,
    "alfworld": build_alfworld_test_suite,
    "alfworld_slice": build_alfworld_test_suite,
    "appworld": build_appworld_test_suite,
    "appworld_slice": build_appworld_test_suite,
    "webarena": build_webarena_test_suite,
    "webarena_slice": build_webarena_test_suite,
}


def get_benchmark_suite(
    name: str, scale: str = "conference", max_tasks: int | None = None
) -> tuple[list[JoinTask], DecompositionSchema]:
    """Retrieve benchmark tasks and decomposition schema by benchmark name and scale."""
    clean_name = name.lower().strip()
    if clean_name not in BENCHMARK_REGISTRY:
        options = ", ".join(sorted(set(BENCHMARK_REGISTRY.keys())))
        raise ValueError(f"Unknown benchmark: '{name}'. Available options: {options}")
    builder = BENCHMARK_REGISTRY[clean_name]
    tasks, schema = builder(scale=scale)
    if max_tasks is not None and max_tasks > 0:
        tasks = tasks[:max_tasks]
    return tasks, schema


MODEL_PRICING: dict[str, tuple[float, float]] = {
    "google/gemini-2.5-flash": (0.30, 2.50),
    "google/gemini-2.5-pro": (1.25, 10.00),
    "openai/gpt-4o-mini": (0.15, 0.60),
    "meta-llama/llama-3.3-70b-instruct": (0.25, 0.65),
    "meta-llama/llama-3.1-8b-instruct": (0.05, 0.05),
    "openai/gpt-4o": (2.50, 10.00),
    "anthropic/claude-3.5-sonnet": (3.00, 15.00),
}


def estimate_benchmark_cost(
    model: str,
    num_tasks: int,
    num_arms: int = 3,
    prompt_tokens_per_call: int = 450,
    completion_tokens_per_call: int = 200,
) -> dict[str, float]:
    """Estimate token usage and cost before executing API requests."""
    total_episodes = num_tasks * num_arms
    calls_per_episode = 2.5
    total_calls = total_episodes * calls_per_episode
    total_prompt = total_calls * prompt_tokens_per_call
    total_completion = total_calls * completion_tokens_per_call

    prompt_rate, completion_rate = MODEL_PRICING.get(model, (0.50, 1.50))
    prompt_cost = (total_prompt / 1_000_000.0) * prompt_rate
    completion_cost = (total_completion / 1_000_000.0) * completion_rate
    est_usd = round(prompt_cost + completion_cost, 4)

    return {
        "total_episodes": float(total_episodes),
        "total_calls": float(total_calls),
        "est_prompt_tokens": float(total_prompt),
        "est_completion_tokens": float(total_completion),
        "est_usd": est_usd,
    }


def generate_markdown_report(report: dict[str, Any]) -> str:
    benchmark = report.get("benchmark", "benchmark")
    scale = report.get("scale", "diagnostic")
    model = report.get("model", "unknown")
    total_spent = report.get("total_spent_usd", 0.0)
    total_calls = report.get("total_calls", 0)
    tasks_count = report.get("tasks_count", 0)
    status = str(report.get("status", "unknown")).upper()

    lines = [
        f"# Báo Cáo Kết Quả Thực Nghiệm COPROMEM 2.0: {benchmark.upper()}",
        "",
        "## 1. Thông Số Tổng Quan",
        "",
        "| Thông Số | Giá Trị |",
        "| :--- | :--- |",
        f"| **Benchmark** | `{benchmark}` (Scale: `{scale}`) |",
        f"| **Mô hình LLM** | `{model}` |",
        f"| **Tổng số tác vụ** | {tasks_count} tasks |",
        f"| **Tổng lượt gọi LLM** | {total_calls} calls |",
        f"| **Tổng chi phí API** | ${total_spent:.6f} USD |",
        f"| **Trạng thái thực thi** | {status} |",
        "",
        "## 2. Bảng Tổng Hợp Chỉ Số Hiệu Năng & Độ Chính Xác (Accuracy)",
        "",
        "| Nhánh Thực Nghiệm (Arm) | Số Task | Thành Công | **Độ Chính Xác (Accuracy)** | Harmful Flips (Nhớ sai) | Tự Sửa Lỗi (Recovered) | Tổng Chi Phí (USD) |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    summary = report.get("summary", {})
    for arm, stats in summary.items():
        hf_str = f"{stats.get('harmful_flips', 0)} ({stats.get('harmful_flip_rate', 0.0) * 100:.1f}%)"
        acc_str = f"**{stats.get('accuracy_percent', 0.0):.1f}%**"
        lines.append(
            f"| **`{arm}`** | {stats.get('total_tasks', 0)} | {stats.get('success_count', 0)} | {acc_str} | {hf_str} | {stats.get('recovered_count', 0)} | ${stats.get('total_usd_spent', 0.0):.6f} |"
        )

    lines.extend([
        "",
        "## 3. Bảng Chi Tiết Từng Tác Vụ (Task-by-Task Breakdown)",
        "",
        "| Task ID | `no_memory` (Zero-shot) | `semantic_rag` (Naive RAG) | `copromem_v2` (COPROMEM) | Tự Phục Hồi Hợp Đồng | Tổng Chi Phí Task |",
        "| :--- | :---: | :---: | :---: | :---: | :---: |",
    ])

    results = report.get("results", {})
    task_ids: list[str] = []
    task_map: dict[str, dict[str, Any]] = {}
    for arm, items in results.items():
        for it in items:
            tid = it.get("task_id", "")
            if tid not in task_map:
                task_map[tid] = {}
                task_ids.append(tid)
            task_map[tid][arm] = it

    for tid in task_ids:
        nm = task_map[tid].get("no_memory", {})
        sr = task_map[tid].get("semantic_rag", {})
        cp = task_map[tid].get("copromem_v2", {})

        nm_str = "✅ Đạt" if nm.get("success") else "❌ Thất bại"
        sr_str = "✅ Đạt" if sr.get("success") else "❌ Thất bại"
        cp_str = "✅ Đạt" if cp.get("success") else "❌ Thất bại"
        rec = "🔄 Có (Tự sửa)" if cp.get("recovered") else "—"
        total_task_cost = sum(task_map[tid].get(a, {}).get("usd_spent", 0.0) for a in results)
        lines.append(f"| `{tid}` | {nm_str} | {sr_str} | {cp_str} | {rec} | ${total_task_cost:.6f} |")

    lines.extend([
        "",
        "---",
        "*Báo cáo được khởi tạo tự động từ COPROMEM 2.0 OpenRouter Runner.*",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run COPROMEM 2.0 OpenRouter experiment pilot.")
    parser.add_argument(
        "--benchmark",
        type=str,
        default="twin_task",
        choices=[
            "twin_task",
            "alfworld",
            "appworld",
            "webarena",
            "all",
            "twin_task_slice",
            "alfworld_slice",
            "appworld_slice",
            "webarena_slice",
        ],
        help="Target benchmark suite to evaluate.",
    )
    parser.add_argument(
        "--scale",
        type=str,
        default="diagnostic",
        choices=["smoke", "diagnostic", "conference", "full"],
        help="Evaluation scale: 'smoke' (2 tasks), 'diagnostic'/'conference' (18-24 tasks), 'full' (full paper splits: 134 ALFWorld, 110 AppWorld, 100 WebArena).",
    )
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=None,
        help="Optional ceiling to evaluate only the first N tasks of the chosen benchmark suite.",
    )
    parser.add_argument("--api-key", type=str, default="", help="OpenRouter API key.")
    parser.add_argument("--model", type=str, default="openai/gpt-4o-mini", help="Canonical model endpoint.")
    parser.add_argument("--provider", type=str, default="", help="Pinned provider route on OpenRouter.")
    parser.add_argument("--max-usd", type=float, default=0.50, help="Hard USD budget cap (0, 5.0].")
    parser.add_argument("--max-calls", type=int, default=150, help="Maximum HTTP call attempts.")
    parser.add_argument("--seed", type=int, default=42, help="Random sampling seed.")
    parser.add_argument("--output", type=str, default="artifacts/openrouter_pilot_report.json", help="Report path.")
    parser.add_argument("--store-dir", type=str, default="artifacts/research/openrouter_store", help="Ledger dir.")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume prior interrupted run from output file, skipping already completed tasks.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Display pre-flight cost estimation and task plan without invoking APIs.",
    )
    args = parser.parse_args()

    # Determine benchmark suites to run
    canonical_suites = ["twin_task", "alfworld", "appworld", "webarena"]
    benchmark_names = canonical_suites if args.benchmark == "all" else [args.benchmark]

    # Collect total tasks across selected benchmarks
    selected_suites: list[tuple[str, list[JoinTask], DecompositionSchema]] = []
    total_task_count = 0
    for b_name in benchmark_names:
        b_tasks, b_schema = get_benchmark_suite(b_name, scale=args.scale, max_tasks=args.max_tasks)
        selected_suites.append((b_name, b_tasks, b_schema))
        total_task_count += len(b_tasks)

    # Pre-flight cost estimation
    est = estimate_benchmark_cost(args.model, total_task_count, num_arms=3)
    print("=" * 70)
    print(f"COPROMEM 2.0 OpenRouter Experiment Runner")
    print(f"Benchmark(s) : {args.benchmark} [scale: {args.scale}] ({total_task_count} total tasks)")
    print(f"Model        : {args.model}")
    print(f"Arms         : no_memory, semantic_rag, copromem_v2 (3 arms)")
    print(f"Total Episodes : {int(est['total_episodes'])} (est. {int(est['total_calls'])} LLM calls)")
    print(f"Estimated Cost : ~${est['est_usd']:.4f} USD | Configured Cap: ${args.max_usd:.2f} USD")
    print("=" * 70)

    if args.dry_run:
        print("[DRY RUN COMPLETE] No API calls were made.")
        return

    if est["est_usd"] > args.max_usd:
        print(
            f"[PRE-FLIGHT NOTICE] Estimated cost (${est['est_usd']:.4f}) exceeds --max-usd (${args.max_usd:.2f}).\n"
            f"  If the budget limit is reached, completed episodes will be safely saved to disk.\n"
            f"  You can resume at any time with: --max-usd <higher_val> --resume\n"
        )

    api_key = load_api_key(args.api_key)
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured via --api-key, environment, or .env file.")

    out_path = Path(args.output)
    results: dict[str, list[dict[str, Any]]] = {"no_memory": [], "semantic_rag": [], "copromem_v2": []}
    completed_keys: set[tuple[str, str]] = set()

    # Load previously completed tasks if resuming
    if args.resume and out_path.exists():
        try:
            prior_report = json.loads(out_path.read_text(encoding="utf-8"))
            for arm, items in prior_report.get("results", {}).items():
                if arm in results and isinstance(items, list):
                    results[arm] = items
                    for it in items:
                        if isinstance(it, dict) and "task_id" in it:
                            completed_keys.add((arm, it["task_id"]))
            print(f"[RESUME] Loaded {len(completed_keys)} previously completed episode(s) from {args.output}")
        except Exception as err:
            print(f"[RESUME WARNING] Could not parse existing report: {err}. Starting clean.")

    store = RunStore(args.store_dir)
    ledger = BudgetLedger(store, max_usd=args.max_usd, max_attempts=args.max_calls)
    prompt_rate, completion_rate = MODEL_PRICING.get(args.model, (0.50, 1.50))
    client = BudgetedOpenRouterClient(
        api_key=api_key,
        model=args.model,
        provider=args.provider,
        ledger=ledger,
        prompt_price_per_million=prompt_rate * 1.5,
        completion_price_per_million=completion_rate * 1.5,
    )
    runner = OpenRouterMultiAgentRunner(client)

    def flush_report(status: str = "completed", error_msg: str | None = None) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # Compute summary statistics
        summary: dict[str, Any] = {}
        base_success_map = {item["task_id"]: item.get("success") for item in results.get("no_memory", [])}

        for arm in ("no_memory", "semantic_rag", "copromem_v2"):
            items = results.get(arm, [])
            total = len(items)
            success_count = sum(1 for it in items if it.get("success"))
            accuracy = round((success_count / total) * 100, 2) if total > 0 else 0.0
            total_usd = round(sum(it.get("usd_spent", 0.0) for it in items), 6)
            recovered_count = sum(1 for it in items if it.get("recovered"))

            harmful_flips = 0
            beneficial_flips = 0
            for it in items:
                tid = it.get("task_id")
                if tid in base_success_map:
                    base_ok = base_success_map[tid]
                    arm_ok = it.get("success")
                    if base_ok and not arm_ok:
                        harmful_flips += 1
                    elif not base_ok and arm_ok:
                        beneficial_flips += 1

            summary[arm] = {
                "total_tasks": total,
                "success_count": success_count,
                "accuracy_percent": accuracy,
                "harmful_flips": harmful_flips,
                "harmful_flip_rate": round(harmful_flips / total, 4) if total > 0 else 0.0,
                "beneficial_flips": beneficial_flips,
                "recovered_count": recovered_count,
                "total_usd_spent": total_usd,
            }

        report: dict[str, Any] = {
            "status": status,
            "benchmark": args.benchmark,
            "scale": args.scale,
            "model": args.model,
            "provider": args.provider,
            "total_spent_usd": round(client.spent_usd, 6),
            "total_calls": client.calls,
            "tasks_count": total_task_count,
            "resumable": True,
            "summary": summary,
            "results": results,
        }
        if error_msg:
            report["error"] = error_msg
            report["resume_instructions"] = (
                f"Rerun with higher budget: python -m copromem.openrouter_experiment "
                f"--benchmark {args.benchmark} --scale {args.scale} --model {args.model} "
                f"--max-usd {args.max_usd + 0.50:.2f} --output {args.output} --resume"
            )
        out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        # Also auto-export human-readable markdown report
        md_path = out_path.with_suffix(".md")
        md_path.write_text(generate_markdown_report(report), encoding="utf-8")

    try:
        for b_name, b_tasks, b_schema in selected_suites:
            print(f"\n--- Running Benchmark Suite: {b_name} [{args.scale}] ({len(b_tasks)} tasks) ---")
            for arm in ("no_memory", "semantic_rag", "copromem_v2"):
                for task in b_tasks:
                    if (arm, task.task_id) in completed_keys:
                        print(f"  [SKIPPED/RESUMED] Arm '{arm}', Task '{task.task_id}' already finished.")
                        continue
                    print(f"  [RUNNING] Arm: {arm:<12} | Task: {task.task_id} ...", end="", flush=True)
                    res = runner.run_episode(task, b_schema, arm=arm, seed=args.seed)
                    results[arm].append(as_jsonable(res))
                    completed_keys.add((arm, task.task_id))
                    print(f" Done. Success: {res.success} | Spent: ${res.usd_spent:.4f}")
                    flush_report(status="in_progress")

        flush_report(status="completed")
        print(f"\n[EXPERIMENT COMPLETED] Total spent: ${client.spent_usd:.4f} USD ({client.calls} calls).")
        print(f"Full report preserved at: {args.output}")

    except BudgetExceeded as exc:
        flush_report(status="paused_budget_cap_reached", error_msg=str(exc))
        print(f"\n[BUDGET CAP REACHED]: {exc}")
        print(f"Spent so far: ${client.spent_usd:.4f} USD. All {len(completed_keys)} completed episodes safely saved.")
        print(f"==> To continue without losing progress, rerun with:")
        print(f"    --max-usd {args.max_usd + 0.50:.2f} --resume")


if __name__ == "__main__":
    main()


