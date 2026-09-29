"""Fail-closed, behavior-based custody classification for v6.1 allocation."""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
from collections import defaultdict
from typing import Any

TASK_ID = re.compile(r"\b[a-f0-9]{7}_\d+\b")
PUBLIC_MENTION_NAMES = {"public-dev-descriptors.json", "train-public-inventory.json"}
HARD_FIELDS = {"history", "after_score", "official_score", "execution_evidence_path", "scorer", "task_state"}
HARD_PATH_PARTS = {"acquisition", "evaluation", "journals", "trajectory-artifacts", "retrievals", "state-machine"}

def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def _ids(value: str) -> set[str]: return set(TASK_ID.findall(value))

def classify(root: pathlib.Path, inventory: pathlib.Path) -> dict[str, Any]:
    """Classify durable evidence without reading benchmark payloads or tasks."""
    rows: dict[str, list[dict[str, str]]] = defaultdict(list)
    for base in (root / "artifacts", root / "research"):
        if not base.exists(): continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".json", ".jsonl", ".md", ".txt", ".log"}: continue
            try: text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError: continue
            found = _ids(text)
            if not found: continue
            relative = str(path.relative_to(root)).replace("\\", "/")
            is_public = path.resolve() == inventory.resolve() or path.name in PUBLIC_MENTION_NAMES
            path_hard = bool(set(path.parts) & HARD_PATH_PARTS)
            parsed: list[dict[str, Any]] = []
            if path.suffix.lower() in {".json", ".jsonl"}:
                for line in ([text] if path.suffix.lower()==".json" else text.splitlines()):
                    try: parsed.append(json.loads(line))
                    except json.JSONDecodeError: pass
            for task_id in found:
                category, reason = "public_mention_only", "public inventory/documentation identifier"
                matched = [obj for obj in parsed if isinstance(obj, dict) and str(obj.get("task_id", "")) == task_id]
                if is_public:
                    category, reason = "public_mention_only", "permitted public inventory"
                elif path_hard:
                    category, reason = "hard_exposed", "durable execution-oriented path"
                elif any(HARD_FIELDS & set(obj) for obj in matched):
                    category, reason = "hard_exposed", "durable task execution/scoring field"
                elif any(isinstance(obj, dict) and obj.get("role", "").startswith("executor:") and task_id in str(obj) for obj in parsed):
                    category, reason = "hard_exposed", "executor settlement evidence"
                elif matched:
                    # A record explicitly scoped to a task but lacking a
                    # recognised public-only or hard-execution marker is
                    # ambiguous and therefore excluded. A task merely nested
                    # in a manifest/candidate list remains a public mention.
                    category, reason = "ambiguous", "task-scoped structured record has unknown custody"
                rows[task_id].append({"path": relative, "category": category, "reason": reason})
    decisions=[]
    for task_id, evidence in sorted(rows.items()):
        categories={item["category"] for item in evidence}
        category = "hard_exposed" if "hard_exposed" in categories else "ambiguous" if "ambiguous" in categories else "public_mention_only"
        decisions.append({"task_id":task_id,"classification":category,"evidence":evidence})
    hard=sorted(row["task_id"] for row in decisions if row["classification"]=="hard_exposed")
    mention=sorted(row["task_id"] for row in decisions if row["classification"]=="public_mention_only")
    ambiguous=sorted(row["task_id"] for row in decisions if row["classification"]=="ambiguous")
    return {"version":"v6.1-behavioral-custody-v1","hard_exclusion":hard,"public_mention_only":mention,"ambiguous_exclusion":ambiguous,
            "hard_exclusion_sha256":digest(hard),"public_mention_only_sha256":digest(mention),"ambiguous_exclusion_sha256":digest(ambiguous),
            "decisions":decisions,"decision_trace_sha256":digest(decisions),"test_normal_prohibited":True}
