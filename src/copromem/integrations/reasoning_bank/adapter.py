"""COPROMEM Adapter for Official ReasoningBank Harness.

Bridges ReasoningBank's native agent runtime with COPROMEM 2.0:
- Pattern Separation Engine (Negative Transfer Veto & Differentiated Contract)
- Recursive Task Decomposer (Hierarchical HTN Milestone Decomposition)
- Subtask-Level Memory Binding
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Ensure project root src is on sys.path
CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parents[2]  # external/reasoning-bank/WebArena -> REPO_ROOT
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from copromem.copromem_memory_module import (
    COPROMEMMemoryModule,
    ProceduralMemoryItem,
)
from copromem.decomposition import RecursiveTaskDecomposer
from copromem.copromem_memory_module import extract_intent_constraints


class COPROMEMReasoningBankAdapter:
    """Seamless bridge providing COPROMEM memory selection to ReasoningBank run.py."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "google/gemini-2.5-flash",
    ) -> None:
        if not api_key:
            api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            # Fallback to .env file
            env_file = REPO_ROOT / ".env"
            if env_file.exists():
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    if line.startswith("OPENROUTER_API_KEY="):
                        api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break

        self.api_key = api_key
        self.model = model
        contract_guidance = os.environ.get("COPROMEM_CONTRACT_GUIDANCE", "false").lower() not in {
            "0", "false", "no", "off",
        }
        self.memory_module = COPROMEMMemoryModule(
            api_key=self.api_key,
            model=self.model,
            include_contract_guidance=contract_guidance,
        )
        self.decomposer: RecursiveTaskDecomposer = self.memory_module.decomposer

    def load_memories(self, jsonl_path: str | Path) -> int:
        """Load accumulated procedural memories from JSONL file."""
        p = Path(jsonl_path)
        if not p.exists():
            return 0
        loaded = 0
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                mem = ProceduralMemoryItem(
                    memory_id=str(data.get("memory_id") or data.get("task_id") or f"mem_{loaded}"),
                    intent=data.get("intent", "") or data.get("query", ""),
                    title=data.get("title", f"Task {data.get('task_id', loaded)} Procedure"),
                    description=data.get("description", ""),
                    procedure=data.get("procedure", "") or "\n".join(data.get("memory_items", [])),
                    domain=data.get("domain", "web_shopping_admin"),
                    constraints=data.get("constraints", {}),
                    is_macro=bool(data.get("is_macro", False)),
                )
                self.memory_module.add_memory(mem)
                loaded += 1
            except Exception as e:
                logger.warning("Failed to parse memory item line: %s", e)
        return loaded

    def select_memory(
        self,
        task_id: str | int,
        query: str,
        memories_jsonl_path: str | Path,
        agent_sys_prompt: str = "",
        domain: str = "web_shopping_admin",
    ) -> str:
        """Execute COPROMEM retrieval with Pattern Separation & Decomposition.

        Returns the formatted prompt string to be written into memory_path.
        """
        # The browser runner starts a fresh process per task. Restore the full
        # slow/fast-memory state rather than reloading only induced text items.
        state_path = Path(memories_jsonl_path).with_name("copromem_state.json")
        if state_path.exists():
            self.memory_module.load_state(json.loads(state_path.read_text(encoding="utf-8")))

        # Retrieve through COPROMEM cognitive architecture
        res = self.memory_module.retrieve_memory(
            arm="copromem_v2",
            task_id=str(task_id),
            intent=query,
            domain=domain,
            agent_prompt_wrapper=agent_sys_prompt,
        )

        state = self.memory_module.export_state()
        state["active_task_id"] = str(task_id)
        state["active_schema_id"] = res.schema.schema_id if res.schema else None
        state_path.write_text(json.dumps(state), encoding="utf-8")
        return res.injected_text or ""

    def complete_episode(
        self,
        task_id: str | int,
        intent: str,
        success: bool,
        actions: list[str],
        memories_jsonl_path: str | Path,
        consolidate: bool = False,
    ) -> None:
        """Persist observed episode evidence and replay after a paired batch."""
        from copromem.webarena_browsergym_benchmark import induce_from_trajectory

        state_path = Path(memories_jsonl_path).with_name("copromem_state.json")
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("active_task_id") != str(task_id):
            raise ValueError(f"COPROMEM state is not for task {task_id}")
        self.memory_module.load_state(state)
        schema_id = state.get("active_schema_id")
        schema = next((s for s in self.memory_module.bank.schemas if s.schema_id == schema_id), None)
        induced = induce_from_trajectory(
            task_id=task_id,
            goal=intent,
            actions=actions,
            success=success,
            schema_id=schema_id,
            domain="web_shopping_admin",
        ) if actions else None
        if induced is not None:
            self.memory_module.add_memory(induced, defer_until_admitted=True)
        self.memory_module.record_episode(
            task_id=str(task_id),
            arm="copromem_v2",
            success=success,
            task_state={"intent": intent, "domain": "web_shopping_admin",
                        "constraints": extract_intent_constraints(intent)},
            schema=schema,
        )
        if consolidate:
            self.memory_module.consolidate_offline(min_priority=0.20)
        new_state = self.memory_module.export_state()
        state_path.write_text(json.dumps(new_state), encoding="utf-8")
