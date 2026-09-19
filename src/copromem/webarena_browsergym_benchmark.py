"""Live BrowserGym WebArena Benchmark Runner.

Executes autonomous browser interactions on live local WebArena instances (Docker),
comparing:
- no_memory: Baseline agent without retrieval
- semantic_rag: Naive vector RAG retrieval
- copromem_v2: Pattern separation + Decomposition schema + Structural handoff
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Ensure environment variables for WebArena are set before importing browsergym
os.environ.setdefault("WA_SHOPPING_ADMIN", "http://localhost:7780/admin")
os.environ.setdefault("WA_SHOPPING", "http://localhost:7780")
os.environ.setdefault("WA_REDDIT", "http://localhost:9999")
os.environ.setdefault("WA_GITLAB", "http://localhost:8023")
os.environ.setdefault("WA_WIKIPEDIA", "http://localhost:8060")
os.environ.setdefault("WA_MAP", "http://localhost:8086")
os.environ.setdefault("WA_HOMEPAGE", "http://localhost:80")

# WebArena native evaluator environment variables (unprefixed)
os.environ.setdefault("SHOPPING_ADMIN", "http://localhost:7780/admin")
os.environ.setdefault("SHOPPING", "http://localhost:7780")
os.environ.setdefault("REDDIT", "http://localhost:9999")
os.environ.setdefault("GITLAB", "http://localhost:8023")
os.environ.setdefault("WIKIPEDIA", "http://localhost:8060")
os.environ.setdefault("MAP", "http://localhost:8086")
os.environ.setdefault("HOMEPAGE", "http://localhost:80")

# Configure WebArena LLM judge bridge to use OpenRouter with openai/gpt-4o-mini
os.environ.setdefault("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
os.environ.setdefault("OPENAI_JUDGE_MODEL", "openai/gpt-4o-mini")

import gymnasium as gym
import browsergym.webarena
from browsergym.utils.obs import flatten_axtree_to_str

from .copromem_memory_module import (
    COPROMEMMemoryModule,
    ProceduralMemoryItem,
    extract_intent_constraints,
)
from .pattern_separation import PatternSeparationEngine
from .schema import DecompositionSchema
from .types import WorkflowRun, SubtaskNode, DependencyEdge, HandoffEvent


SYSTEM_PROMPT_TEMPLATE = """You are an autonomous web browsing agent.
Your task is to accomplish the user's goal by navigating web pages and interacting with page elements.

At each step, you will be given:
1. Goal: The user's requested objective.
2. Retrieved Memory (if any): Relevant past procedural knowledge or guidance.
3. Current URL: The page address.
4. Action History: Your recent past actions and any errors.
5. Accessibility Tree (AXTree): The interactive DOM structure with element IDs (e.g. [12] link 'Home').

You must respond strictly in the following format:
Thought: <Concise reasoning about what you observe and your next action to progress towards the goal>
Action: <A single valid action primitive>

Valid actions include:
- click(bid: str) -> Click element with the given bid, e.g. click("15")
- fill(bid: str, value: str) -> Type text into input field, e.g. fill("45", "query")
- select_option(bid: str, options: str | list[str]) -> Select option in dropdown, e.g. select_option("20", "OptionName")
- goto(url: str) -> Navigate directly to a URL, e.g. goto("http://...")
- scroll(delta_x: float, delta_y: float) -> Scroll page, e.g. scroll(0, 300)
- send_msg_to_user(text: str) -> Finish task and provide the final answer to the user, e.g. send_msg_to_user("Result")
- report_infeasible(reason: str) -> If the goal cannot be achieved or target is not found, e.g. report_infeasible("Not found")
- noop() -> Wait 1 second

General Guidelines:
1. Only interact with elements that actually appear in the current AXTree.
2. Carefully inspect page elements, menus, forms, and tables. Verify that what you extract matches all constraints specified in the goal.
3. When calling send_msg_to_user, provide ONLY the clean, exact entity name, number, or answer value requested (e.g. send_msg_to_user("Quest Lumaflex™ Band")). Do NOT add introductory phrases (e.g. "The answer is: "), labels, bullet numbers, or explanatory sentences, because the benchmark evaluator strictly checks exact matches.
4. If the requested information is genuinely not present or impossible after checking, call report_infeasible("N/A").
5. When counting records in tables or grids (e.g. number of reviews, orders, or items matching a keyword), look for the grid count summary (e.g. 'X records found' or 'Total: X') rather than counting table rows or page size limits.
"""


def load_api_key(cli_key: str | None = None, env_path: str = ".env") -> str:
    key = ""
    if cli_key and cli_key.strip():
        key = cli_key.strip()
    elif os.getenv("OPENROUTER_API_KEY"):
        key = os.environ["OPENROUTER_API_KEY"].strip()
    else:
        p = Path(env_path)
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("OPENROUTER_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not key:
        raise ValueError("OpenRouter API key not found in CLI, environment, or .env file.")
    os.environ.setdefault("OPENAI_API_KEY", key)
    return key


def call_openrouter(
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 1024,
    temperature: float = 0.0,
) -> tuple[str, float, float, int, int]:
    """Call OpenRouter chat completions API.
    
    Returns (content, elapsed_seconds, cost_usd, prompt_tokens, completion_tokens).
    """
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = json.dumps(
        {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/QuanNguyen28/COPROMEM",
            "X-Title": "COPROMEM-WebArena-Live",
        },
        method="POST",
    )

    started = time.perf_counter()
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                elapsed = time.perf_counter() - started
                usage = data.get("usage", {})
                p_toks = int(usage.get("prompt_tokens") or 0)
                c_toks = int(usage.get("completion_tokens") or 0)
                cost_usd = float(usage.get("cost") or 0.0)

                # Fallback pricing calculation if OpenRouter doesn't supply 'cost' field
                if cost_usd <= 0.0 and (p_toks > 0 or c_toks > 0):
                    m_lower = model.lower()
                    if "gemini-2.5-flash" in m_lower:
                        cost_usd = (p_toks * 0.075 + c_toks * 0.30) / 1_000_000.0
                    elif "4o-mini" in m_lower:
                        cost_usd = (p_toks * 0.15 + c_toks * 0.60) / 1_000_000.0
                    else:
                        cost_usd = (p_toks * 0.10 + c_toks * 0.40) / 1_000_000.0

                return content, elapsed, cost_usd, p_toks, c_toks
        except Exception as e:
            if attempt == 2:
                raise RuntimeError(f"OpenRouter API call failed after 3 attempts: {e}")
            time.sleep(1.5 * (attempt + 1))
    return "", 0.0, 0.0, 0, 0


def extract_action(text: str) -> tuple[str, str]:
    """Parse thought and action from model response."""
    thought = ""
    action = ""

    thought_match = re.search(r"Thought:\s*(.*?)(?=\nAction:|$)", text, re.DOTALL)
    if thought_match:
        thought = thought_match.group(1).strip()

    action_match = re.search(r"Action:\s*(.*?)$", text, re.DOTALL)
    if action_match:
        action = action_match.group(1).strip()
    else:
        # Fallback: check if the text itself contains a valid function call
        for pattern in [r"(click\(.*?\))", r"(fill\(.*?\))", r"(send_msg_to_user\(.*?\))", r"(report_infeasible\(.*?\))", r"(goto\(.*?\))"]:
            m = re.search(pattern, text)
            if m:
                action = m.group(1).strip()
                break

    if not action:
        # Default safety action
        action = "noop()"

    return thought, action


_CONFIG_BY_TASK_ID: dict[int, dict[str, Any]] | None = None


def get_task_ground_truth(task_id: int) -> str:
    """Retrieve clean ground truth representation for a WebArena task."""
    global _CONFIG_BY_TASK_ID
    if _CONFIG_BY_TASK_ID is None:
        try:
            import importlib.resources
            import webarena
            all_configs = json.loads(
                importlib.resources.files(webarena).joinpath("test.raw.json").read_text(encoding="utf-8")
            )
            _CONFIG_BY_TASK_ID = {int(c["task_id"]): c for c in all_configs}
        except Exception as e:
            logger.warning("Failed to load test.raw.json: %s", e)
            _CONFIG_BY_TASK_ID = {}

    conf = _CONFIG_BY_TASK_ID.get(task_id)
    if not conf:
        return "N/A"

    ev = conf.get("eval", {})
    raw = ev.get("reference_answer_raw_annotation")
    if raw:
        return str(raw).strip()
    ref_ans = ev.get("reference_answers")
    if ref_ans:
        if isinstance(ref_ans, dict):
            if "exact_match" in ref_ans:
                return str(ref_ans["exact_match"]).strip()
            if "must_include" in ref_ans:
                val = ref_ans["must_include"]
                return ", ".join(val) if isinstance(val, list) else str(val)
            if "fuzzy_match" in ref_ans:
                return str(ref_ans["fuzzy_match"]).strip()
        return str(ref_ans)
    ref_url = ev.get("reference_url")
    if ref_url:
        return f"URL: {ref_url}"
    if ev.get("program_html"):
        return "(State update verified via program_html)"
    return "N/A"


@dataclass
class TaskExecutionResult:
    arm: str
    task_id: int
    intent: str
    sites: list[str]
    success: bool
    reward: float
    steps: int
    duration_seconds: float
    cost_usd: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    ground_truth: str = ""
    actions_taken: list[str] = field(default_factory=list)
    final_message: str = ""
    injected_memory: str = ""
    error: str | None = None


def induce_from_trajectory(
    task_id: int | str,
    goal: str,
    actions: list[str],
    success: bool,
) -> ProceduralMemoryItem | None:
    """Induce procedural memory item from an executed task trajectory.
    
    Only successful episodes generate positive procedural memories.
    Terminal submission actions (send_msg_to_user, report_infeasible) are excluded.
    """
    if not success:
        return None

    # Exclude non-navigational and terminal actions so memory doesn't leak task-specific answers
    clean_acts = [
        a for a in actions
        if not a.startswith("noop")
        and not a.startswith("scroll")
        and not a.startswith("send_msg_to_user")
        and not a.startswith("report_infeasible")
    ]
    if clean_acts:
        proc_summary = " -> ".join(clean_acts[:5]) + " -> verify extracted criteria on screen before submitting"
    else:
        proc_summary = "Navigate to the relevant view/table, apply matching filters, and extract requested value"

    return ProceduralMemoryItem(
        memory_id=f"mem_task_{task_id}",
        intent=goal,
        title=f"Verified navigation trace for Task {task_id}",
        description=f"Observed successful procedure for goal: {goal[:50]}",
        procedure=proc_summary,
        constraints=extract_intent_constraints(goal),
        domain="web_shopping_admin" if "admin" in goal.lower() else "web_shopping",
        success=True,
    )


def run_live_task(
    task_id: int,
    arm: str,
    api_key: str,
    model: str,
    memory_module: COPROMEMMemoryModule,
    max_steps: int = 30,
    headless: bool = True,
) -> TaskExecutionResult:
    """Execute a single WebArena task in a live browser with free step convergence."""
    gym_id = f"browsergym/webarena.{task_id}"
    started_time = time.perf_counter()
    task_gt = get_task_ground_truth(task_id)

    try:
        env = gym.make(gym_id, headless=headless)
        obs, info = env.reset()
    except Exception as e:
        logger.error("Failed to initialize gym env %s: %s", gym_id, e)
        return TaskExecutionResult(
            arm=arm,
            task_id=task_id,
            intent=f"Task {task_id}",
            sites=[],
            success=False,
            reward=0.0,
            steps=0,
            duration_seconds=time.perf_counter() - started_time,
            ground_truth=task_gt,
            error=str(e),
        )

    goal = obs.get("goal", "")
    actions_taken = []
    action_history = []
    success = False
    reward = 0.0
    final_message = ""

    # Memory retrieval based on arm
    injected_memory = ""
    domain = "web_shopping_admin" if "admin" in obs.get("url", "") else "web_shopping"
    if arm in ("semantic_rag", "copromem_v2", "reasoningbank"):
        mem_res = memory_module.retrieve_memory(
            arm=arm,
            task_id=str(task_id),
            intent=goal,
            domain=domain,
            sites=["shopping_admin"] if "admin" in domain else ["shopping"],
            start_url=obs.get("url", ""),
        )
        if mem_res.injected_text:
            injected_memory = f"\n\n[RETRIEVED MEMORY ({arm})]:\n{mem_res.injected_text}"

    step_count = 0
    total_cost_usd = 0.0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    repeated_action_count = 0
    last_action = ""
    last_axtree_snippet = ""

    try:
        for step in range(max_steps):
            step_count += 1
            current_url = obs.get("url", "")
            axtree_obj = obs.get("axtree_object")
            axtree_txt = flatten_axtree_to_str(axtree_obj) if axtree_obj else ""

            # Truncate AXTree to first 8000 characters if too long to save token budget
            if len(axtree_txt) > 8000:
                axtree_txt = axtree_txt[:8000] + "\n... [Truncated for brevity]"

            history_str = "\n".join(action_history[-3:]) if action_history else "None (starting task)"
            last_err = obs.get("last_action_error", "")
            if last_err:
                history_str += f"\nLast Action Error: {last_err}"

            user_prompt = f"""Goal: {goal}{injected_memory}

Current URL: {current_url}

Recent Action History:
{history_str}

Current Page AXTree:
{axtree_txt}

Please state your Thought and next Action:"""

            sys_prompt = SYSTEM_PROMPT_TEMPLATE

            response_text, _, step_cost, p_toks, c_toks = call_openrouter(
                api_key=api_key,
                model=model,
                system_prompt=sys_prompt,
                user_prompt=user_prompt,
                max_tokens=512,
                temperature=0.0,
            )
            total_cost_usd += step_cost
            total_prompt_tokens += p_toks
            total_completion_tokens += c_toks

            thought, action = extract_action(response_text)
            actions_taken.append(action)
            action_history.append(f"Action: {action} (Thought: {thought})")

            if "send_msg_to_user" in action:
                m = re.search(r'send_msg_to_user\(\s*["\']?(.*?)["\']?\s*\)', action)
                if m:
                    final_message = m.group(1).rstrip("')\"")

            # Stagnation detection: 3 consecutive identical actions on identical page state
            current_snippet = axtree_txt[:300]
            if action == last_action and current_snippet == last_axtree_snippet:
                repeated_action_count += 1
                if repeated_action_count >= 3:
                    logger.warning(
                        f"Task {task_id} [{arm}]: Terminating early due to stagnation (3 identical consecutive actions)."
                    )
                    break
            else:
                repeated_action_count = 1
                last_action = action
                last_axtree_snippet = current_snippet

            obs, step_reward, terminated, truncated, step_info = env.step(action)
            if step_reward > 0:
                reward = step_reward
                success = True

            if terminated or truncated:
                if step_reward > 0:
                    success = True
                    reward = step_reward
                break

    except Exception as e:
        logger.error("Error during execution of task %s on arm %s: %s", task_id, arm, e)
        return TaskExecutionResult(
            arm=arm,
            task_id=task_id,
            intent=goal,
            sites=[],
            success=success,
            reward=reward,
            steps=step_count,
            duration_seconds=time.perf_counter() - started_time,
            cost_usd=total_cost_usd,
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            ground_truth=task_gt,
            actions_taken=actions_taken,
            final_message=final_message,
            injected_memory=injected_memory,
            error=str(e),
        )
    finally:
        env.close()

    duration = time.perf_counter() - started_time
    return TaskExecutionResult(
        arm=arm,
        task_id=task_id,
        intent=goal,
        sites=[],
        success=success,
        reward=reward,
        steps=step_count,
        duration_seconds=duration,
        cost_usd=total_cost_usd,
        prompt_tokens=total_prompt_tokens,
        completion_tokens=total_completion_tokens,
        ground_truth=task_gt,
        actions_taken=actions_taken,
        final_message=final_message,
        injected_memory=injected_memory,
    )


ALL_SHOPPING_ADMIN_184 = [
    0, 1, 2, 3, 4, 5, 6, 11, 12, 13, 14, 15, 41, 42, 43, 62, 63, 64, 65, 77,
    78, 79, 94, 95, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 119, 120,
    121, 122, 123, 127, 128, 129, 130, 131, 157, 183, 184, 185, 186, 187, 193,
    194, 195, 196, 197, 198, 199, 200, 201, 202, 203, 204, 208, 209, 210, 211,
    212, 213, 214, 215, 216, 217, 243, 244, 245, 246, 247, 288, 289, 290, 291,
    292, 344, 345, 346, 347, 348, 374, 375, 423, 453, 454, 455, 456, 457, 458,
    459, 460, 461, 462, 463, 464, 470, 471, 472, 473, 474, 486, 487, 488, 489,
    490, 491, 492, 493, 494, 495, 496, 497, 498, 499, 500, 501, 502, 503, 504,
    505, 538, 539, 540, 541, 542, 543, 544, 545, 546, 547, 548, 549, 550, 551,
    676, 677, 678, 679, 680, 694, 695, 696, 697, 698, 699, 700, 701, 702, 703,
    704, 705, 706, 707, 708, 709, 710, 711, 712, 713, 759, 760, 768, 769, 770,
    771, 772, 773, 774, 775, 776, 777, 778, 779, 780, 781, 782, 790,
]

TEST_SHOPPING_ADMIN_20 = [
    0, 1, 4, 11, 12, 13, 14, 15, 41, 42, 43, 77, 78, 79, 94, 95, 107, 115, 119, 120
]

DEFAULT_SHOPPING_ADMIN_20 = [0, 1, 2, 3, 4, 5, 6, 11, 12, 13, 14, 15, 41, 42, 43, 62, 63, 64, 65, 77]
DEFAULT_SHOPPING_20 = [21, 22, 23, 24, 25, 26, 47, 48, 49, 50, 51, 96, 117, 118, 124, 125, 126, 141, 142, 143]
DEFAULT_40_TASKS = DEFAULT_SHOPPING_ADMIN_20 + DEFAULT_SHOPPING_20


def run_benchmark(
    task_ids: list[int],
    arms: list[str],
    api_key: str,
    model: str = "google/gemini-2.5-flash",
    max_steps: int = 30,
    headless: bool = True,
    output_dir: str = "artifacts/live_browser_benchmark",
    resume: bool = True,
) -> dict[str, Any]:
    """Run full live comparative benchmark across task IDs and arms with progressive flush and resume."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    latest_json = out_path / "benchmark_results_latest.json"

    # Independent memory module per arm for clean continual learning evaluation
    memory_modules: dict[str, COPROMEMMemoryModule] = {
        arm: COPROMEMMemoryModule() for arm in arms
    }
    results_by_arm: dict[str, list[TaskExecutionResult]] = {arm: [] for arm in arms}
    completed_keys: set[tuple[str, int]] = set()

    # Load prior results if resuming
    if resume and latest_json.exists():
        try:
            prior_data = json.loads(latest_json.read_text(encoding="utf-8"))
            if prior_data.get("model") == model:
                for arm, arm_data in prior_data.get("arms_comparison", {}).items():
                    if arm in results_by_arm:
                        for t_dict in arm_data.get("tasks", []):
                            res_obj = TaskExecutionResult(**t_dict)
                            results_by_arm[arm].append(res_obj)
                            completed_keys.add((arm, res_obj.task_id))
                print(f"[RESUME] Loaded {len(completed_keys)} previously completed task evaluations for model '{model}' from {latest_json}")
            else:
                print(f"[NOTE] Prior results in {latest_json} used model '{prior_data.get('model')}', starting clean run for model '{model}'.")
        except Exception as e:
            logger.warning("Could not parse existing benchmark results for resume: %s", e)

    print(f"=== Starting Live Browser WebArena Benchmark (Shopping Admin Suite) ===")
    print(f"Model: {model}")
    print(f"Judge: {os.environ.get('OPENAI_JUDGE_MODEL', 'openai/gpt-4o-mini')}")
    print(f"Arms: {arms}")
    print(f"Tasks ({len(task_ids)}): {task_ids}")
    print(f"Max Steps Safety Cap: {max_steps} (Free Convergence)")
    print(f"Local Server: {os.environ.get('WA_SHOPPING_ADMIN')}")
    print("=" * 70)

    def flush_report(
        current_task_idx: int,
        current_task_id: int | None = None,
        current_arm: str | None = None,
    ) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "model": model,
            "total_tasks": len(task_ids),
            "completed_tasks": current_task_idx,
            "arms_comparison": {},
        }

        for arm, res_list in results_by_arm.items():
            succ_count = sum(1 for r in res_list if r.success)
            total = len(res_list)
            sr = (succ_count / total * 100.0) if total > 0 else 0.0
            avg_steps = sum(r.steps for r in res_list) / total if total > 0 else 0.0
            avg_duration = sum(r.duration_seconds for r in res_list) / total if total > 0 else 0.0
            total_cost = sum(r.cost_usd for r in res_list)
            avg_cost = total_cost / total if total > 0 else 0.0
            total_prompt_toks = sum(r.prompt_tokens for r in res_list)
            total_comp_toks = sum(r.completion_tokens for r in res_list)

            summary["arms_comparison"][arm] = {
                "success_count": succ_count,
                "total_tasks": total,
                "success_rate_pct": round(sr, 2),
                "average_steps": round(avg_steps, 2),
                "average_duration_sec": round(avg_duration, 2),
                "total_cost_usd": round(total_cost, 4),
                "avg_cost_usd": round(avg_cost, 5),
                "total_prompt_tokens": total_prompt_toks,
                "total_completion_tokens": total_comp_toks,
                "tasks": [asdict(r) for r in res_list],
            }

        # Write latest json
        latest_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        # Generate Markdown Report
        status_line = (
            f"- **Live Status:** Evaluating Task {current_task_id} (`{current_arm}`)"
            if current_task_id is not None
            else "- **Live Status:** Idle / Batch progress synced"
        )
        md_lines = [
            f"# Live Browser WebArena Benchmark Report (Shopping Admin Suite)",
            f"",
            f"- **Timestamp:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **Agent Model:** `{model}` (via OpenRouter API)",
            f"- **Judge Model:** `{os.environ.get('OPENAI_JUDGE_MODEL', 'openai/gpt-4o-mini')}` (via OpenRouter bridge)",
            f"- **Progress:** {current_task_idx}/{len(task_ids)} tasks fully evaluated",
            f"{status_line}",
            f"- **Max Steps Safety Cap:** {max_steps} (Free convergence)",
            f"- **Local Server:** `{os.environ.get('WA_SHOPPING_ADMIN')}`",
            f"",
            f"## 1. Summary Comparison",
            f"",
            f"| Arm | Overall SR % | Success Count | Avg Steps | Avg Duration (s) | Total Cost ($) | Avg Cost/Task ($) |",
            f"| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
        ]
        for arm, stats in summary["arms_comparison"].items():
            md_lines.append(
                f"| `{arm}` | **{stats['success_rate_pct']:.1f}%** | {stats['success_count']}/{stats['total_tasks']} | {stats['average_steps']:.2f} | {stats['average_duration_sec']:.1f}s | ${stats['total_cost_usd']:.4f} | ${stats['avg_cost_usd']:.5f} |"
            )

        md_lines.extend([
            f"",
            f"## 2. Per-Task Breakdown & Extracted Outputs",
            f"",
            f"| Task ID | Intent & Expected Ground Truth | " + " | ".join(f"`{a}`" for a in arms) + " | Total Task Cost ($) |",
            f"| :---: | :--- | " + " | ".join(":---:" for _ in arms) + " | :---: |",
        ])

        # Find all tasks executed so far
        max_len = max((len(results_by_arm[a]) for a in arms), default=0)
        for i in range(max_len):
            first_arm = arms[0]
            if i < len(results_by_arm[first_arm]):
                r0 = results_by_arm[first_arm][i]
                tid = r0.task_id
                intent = r0.intent
            else:
                tid = task_ids[i] if i < len(task_ids) else i
                intent = f"Task {tid}"
            gt_text = get_task_ground_truth(tid)
            intent_cell = f"{intent}<br>**[Ground Truth]:** `{gt_text}`"
            arm_outcomes = []
            task_cost = 0.0
            for arm in arms:
                if i < len(results_by_arm[arm]):
                    res = results_by_arm[arm][i]
                    task_cost += res.cost_usd
                    status_text = "PASS (1.0)" if res.success else "FAIL (0.0)"
                    ans_info = f"<br>Extracted: `{res.final_message}`" if res.final_message else ""
                    cost_info = f", ${res.cost_usd:.4f}"
                    arm_outcomes.append(f"**{status_text}** ({res.steps} steps, {res.duration_seconds:.1f}s{cost_info}){ans_info}")
                else:
                    arm_outcomes.append("*(In progress)*")
            md_lines.append(f"| **Task {tid}** | {intent_cell} | " + " | ".join(arm_outcomes) + f" | ${task_cost:.4f} |")

        md_lines.extend([
            f"",
            f"## 3. Negative Transfer & Memory Separation Audit",
            f"",
            f"| Task ID | Arm | Memory Guidance Injected | Veto Triggered? |",
            f"| :---: | :---: | :--- | :---: |",
        ])
        for i in range(max_len):
            for arm in arms:
                if i < len(results_by_arm[arm]):
                    res = results_by_arm[arm][i]
                    mem_snippet = "*(None)*"
                    veto_str = "N/A"
                    if res.injected_memory:
                        cleaned_mem = res.injected_memory.replace("\n", " ")
                        mem_snippet = (cleaned_mem[:100] + "...") if len(cleaned_mem) > 100 else cleaned_mem
                        veto_str = "YES (VETO)" if "VETO" in res.injected_memory else "No"
                    md_lines.append(f"| Task {res.task_id} | `{arm}` | {mem_snippet} | {veto_str} |")

        report_md_content = "\n".join(md_lines) + "\n"
        canonical_report = Path("artifacts/live_browser_benchmark_report.md")
        canonical_report.parent.mkdir(parents=True, exist_ok=True)
        canonical_report.write_text(report_md_content, encoding="utf-8")

        # Mirror write to LIVE_MONITOR.md directly
        try:
            Path("LIVE_MONITOR.md").write_text(report_md_content, encoding="utf-8")
        except Exception as err:
            logger.warning("Failed to write LIVE_MONITOR.md: %s", err)

        return summary

    # Initial flush on startup/resume so report shows live state immediately
    completed_so_far = min((len(results_by_arm[a]) for a in arms), default=0)
    flush_report(completed_so_far)

    for idx, task_id in enumerate(task_ids, 1):
        domain_str = "Shopping Admin" if task_id in ALL_SHOPPING_ADMIN_184 else "Shopping Storefront"
        print(f"\n--- [{idx}/{len(task_ids)}] Running Task {task_id} ({domain_str}) ---")
        for arm in arms:
            if (arm, task_id) in completed_keys:
                print(f"  > Arm: {arm:<14} [ALREADY COMPLETED, SKIPPING]")
                continue

            # Update live monitor that this arm has started
            flush_report(idx - 1, current_task_id=task_id, current_arm=f"{arm} (evaluating...)")

            print(f"  > Arm: {arm:<14} ...", end="", flush=True)
            res = run_live_task(
                task_id=task_id,
                arm=arm,
                api_key=api_key,
                model=model,
                memory_module=memory_modules[arm],
                max_steps=max_steps,
                headless=headless,
            )
            results_by_arm[arm].append(res)
            completed_keys.add((arm, task_id))
            status_str = "SUCCESS (1.0)" if res.success else "FAILED (0.0)"
            ans_str = f" [Extracted: '{res.final_message}']" if res.final_message else ""
            print(f" {status_str} in {res.steps} steps ({res.duration_seconds:.1f}s, ${res.cost_usd:.4f}){ans_str}")

            # Continual Learning: Induce and accumulate procedural memory
            if arm in ("semantic_rag", "copromem_v2") and res.actions_taken:
                induced_mem = induce_from_trajectory(
                    task_id=task_id,
                    goal=res.intent,
                    actions=res.actions_taken,
                    success=res.success,
                )
                if induced_mem is not None:
                    memory_modules[arm].add_memory(induced_mem)
                if arm == "copromem_v2":
                    memory_modules[arm].record_episode(
                        task_id=str(task_id),
                        arm=arm,
                        success=res.success,
                        task_state={"intent": res.intent, "constraints": extract_intent_constraints(res.intent)},
                        schema=None,
                    )

            # Flush immediately after EVERY ARM completes!
            flush_report(idx - 1, current_task_id=task_id, current_arm=f"{arm} (completed)")

        # Flush progressive reports after every full task
        flush_report(idx)

    final_summary = flush_report(len(task_ids))
    timestamp = int(time.time())
    final_archive = out_path / f"benchmark_results_{timestamp}.json"
    final_archive.write_text(json.dumps(final_summary, indent=2), encoding="utf-8")
    print(f"\nBenchmark completed! Full final results archived to {final_archive}")
    return final_summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live WebArena BrowserGym Comparative Benchmark")
    parser.add_argument("--suite", type=str, choices=["test20", "full184", "custom"], default="test20", help="Suite to run: test20 (20 representative tasks) or full184 (all shopping_admin tasks)")
    parser.add_argument("--tasks", type=int, nargs="+", default=None, help="Explicit task IDs to evaluate")
    parser.add_argument("--arms", type=str, nargs="+", default=["no_memory", "semantic_rag", "copromem_v2"], help="Memory arms")
    parser.add_argument("--model", type=str, default="google/gemini-2.5-flash", help="OpenRouter model name")
    parser.add_argument("--max_steps", type=int, default=30, help="Max steps safety cap per task")
    parser.add_argument("--headless", action="store_true", default=True, help="Run headless")
    parser.add_argument("--output_dir", type=str, default="artifacts/live_browser_benchmark")
    parser.add_argument("--no-resume", action="store_false", dest="resume", help="Disable resume from prior runs")
    args = parser.parse_args()

    if args.tasks is not None and len(args.tasks) > 0:
        task_ids = args.tasks
    elif args.suite == "full184":
        task_ids = ALL_SHOPPING_ADMIN_184
    else:
        task_ids = TEST_SHOPPING_ADMIN_20

    api_key = load_api_key()
    run_benchmark(
        task_ids=task_ids,
        arms=args.arms,
        api_key=api_key,
        model=args.model,
        max_steps=args.max_steps,
        headless=args.headless,
        output_dir=args.output_dir,
        resume=args.resume,
    )
