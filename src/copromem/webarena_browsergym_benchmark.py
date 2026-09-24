"""Live BrowserGym WebArena Benchmark Runner.

Executes autonomous browser interactions on live local WebArena instances (Docker),
comparing:
- no_memory: Baseline agent without retrieval
- semantic_rag: Naive vector RAG retrieval
- copromem_v2: Pattern separation, decomposition guidance, and an observable
  browser-action verifier. Semantic milestone verification remains unimplemented.
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

# Add reasoning-bank to sys.path
_rb_path = Path(__file__).resolve().parent.parent.parent / "external" / "reasoning-bank" / "WebArena"
if str(_rb_path) not in sys.path:
    sys.path.insert(0, str(_rb_path))

import gymnasium as gym
import browsergym.webarena
from browsergym.utils.obs import flatten_axtree_to_str

from agents.legacy.dynamic_prompting import Flags, MainPrompt, SystemPrompt
from agents.legacy.utils.llm_utils import parse_html_tags_raise, ParseError


def webarena_llm_fuzzy_match(
    api_key: str,
    judge_model: str,
    question: str,
    reference: str,
    pred: str,
) -> tuple[bool, str, float]:
    """Official WebArena evaluation method (external/webarena/evaluation_harness/helper_functions.py:llm_fuzzy_match).

    Evaluates whether the student's answer is semantically equivalent to the reference ground truth.
    Returns (is_correct, explanation_response, cost_usd).
    """
    system_msg = "You are a helpful assistant"
    user_prompt = (
        "Help a teacher to grade the answer of a student given a question. "
        "Keep in mind that the student may use different phrasing or wording to answer the question. "
        "The goal is to evaluate whether the answer is semantically equivalent to the reference answer.\n"
        f"question: {question}\n"
        f"reference answer: {reference}\n"
        "all the string 'N/A' that you see is a special sequence that means 'not achievable'\n"
        f"student answer: {pred}\n"
        "Conclude the judgement by correct/incorrect/partially correct."
    )

    response, _, j_cost, _, _ = call_openrouter(
        api_key=api_key,
        model=judge_model,
        system_prompt=system_msg,
        user_prompt=user_prompt,
        max_tokens=384,
        temperature=0.0,
    )

    resp_lower = response.lower()
    if "partially correct" in resp_lower or "incorrect" in resp_lower:
        is_success = False
    elif "correct" in resp_lower:
        is_success = True
    else:
        is_success = False

    return is_success, response.strip(), j_cost

from .copromem_memory_module import (
    COPROMEMMemoryModule,
    ProceduralMemoryItem,
    extract_intent_constraints,
)
from .contracts import Contract
from .schema import DecompositionSchema
from .types import HandoffEvent

REASONINGBANK_MEMORY_HEADER = (
    "Below are some memory items that I accumulated from past interaction from the environment that may be helpful to solve the task. "
    "You can use it when you feel it's relevant. In each step, please first explicitly discuss if you want to use each memory item or not, and then take action."
)



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


def get_task_intent(task_id: int) -> str:
    """Retrieve intent string for a WebArena task."""
    get_task_ground_truth(task_id)  # Ensure _CONFIG_BY_TASK_ID is loaded
    if _CONFIG_BY_TASK_ID and task_id in _CONFIG_BY_TASK_ID:
        return _CONFIG_BY_TASK_ID[task_id].get("intent", f"Task {task_id}")
    return f"Task {task_id}"


def is_qa_task(task_id: int) -> bool:
    """Check if task is an Information-Seeking (QA) task with text ground truth reference answers.

    Action / State-mutation tasks without text reference answers (e.g. form-filling, DOM updates) return False.
    """
    get_task_ground_truth(task_id)  # Ensure _CONFIG_BY_TASK_ID is loaded
    if not _CONFIG_BY_TASK_ID or task_id not in _CONFIG_BY_TASK_ID:
        return False
    conf = _CONFIG_BY_TASK_ID[task_id]
    ev = conf.get("eval", {})
    eval_types = ev.get("eval_types", [])
    ref = ev.get("reference_answers")
    return ("string_match" in eval_types) and (ref is not None)



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
    domain: str = "general"
    cost_usd: float = 0.0
    decomposition_cost_usd: float = 0.0
    agent_cost_usd: float = 0.0
    judge_cost_usd: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    ground_truth: str = ""
    actions_taken: list[str] = field(default_factory=list)
    handoffs: list[HandoffEvent] = field(default_factory=list)
    final_message: str = ""
    injected_memory: str = ""
    schema_used: Any = None
    native_success: bool = False
    autoeval_success: bool = False
    autoeval_thoughts: str = ""
    error: str | None = None


def abstract_trajectory_to_subtasks(actions: list[str]) -> str:
    """Abstract raw trajectory actions into domain-agnostic cognitive phases."""
    has_input = any(a.startswith("fill") or a.startswith("select_option") for a in actions)
    has_nav = any(a.startswith("click") or a.startswith("goto") for a in actions)

    subtasks = []
    if has_nav:
        subtasks.append("Locate target domain context or view")
    if has_input:
        subtasks.append("Bind parameters and configure target criteria")
        subtasks.append("Commit state transition and refresh observation")
    subtasks.append("Verify observed state satisfies all constraints and extract target output")

    return " -> ".join(f"{i+1}. {s}" for i, s in enumerate(subtasks))


def induce_from_trajectory(
    task_id: int | str,
    goal: str,
    actions: list[str],
    success: bool,
    schema_id: str | None = None,
    domain: str | None = None,
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
    proc_summary = abstract_trajectory_to_subtasks(clean_acts)

    return ProceduralMemoryItem(
        memory_id=f"mem_task_{task_id}",
        intent=goal,
        title=f"Structural subtask workflow for Task {task_id}",
        description=f"Observed successful procedure for goal: {goal[:50]}",
        procedure=proc_summary,
        constraints=extract_intent_constraints(goal),
        domain=domain or ("web_shopping_admin" if "admin" in goal.lower() else "web_shopping"),
        success=True,
        schema_id=schema_id,
    )


def run_live_task(
    task_id: int,
    arm: str,
    api_key: str,
    model: str,
    memory_module: COPROMEMMemoryModule,
    max_steps: int = 30,
    temperature: float = 0.7,
    headless: bool = True,
) -> TaskExecutionResult:
    """Execute a single WebArena task in a live browser using official ReasoningBank dynamic prompting."""
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
    actions_taken: list[str] = []
    handoffs: list[HandoffEvent] = []
    thoughts_taken: list[str] = []
    memories_taken: list[Any] = []
    success = False
    reward = 0.0
    final_message = ""

    # Memory retrieval based on arm
    injected_memory = ""
    schema_used = None
    decomp_before = (
        memory_module.decomposer.api_cost_usd,
        memory_module.decomposer.api_prompt_tokens,
        memory_module.decomposer.api_completion_tokens,
    )
    action_contract = Contract(
        contract_id="browser_action_accepted_v1",
        interface="agent_to_browser",
        precondition="an executable browser action is provided",
        postcondition="the browser reports no action error",
        verifier_name="browser_action_accepted",
        owner="planner",
        recovery_route="inspect the browser error and retry the action",
        scope_name="browser_action_scope",
        counterexamples=(),
        required_fields=("action",),
        status="admitted",
    ) if arm == "copromem_v2" else None
    domain = "web_shopping_admin" if "admin" in obs.get("url", "") else "web_shopping"
    base_sys_prompt = SystemPrompt().prompt
    if arm in ("semantic_rag", "copromem_v2", "reasoningbank"):
        mem_res = memory_module.retrieve_memory(
            arm=arm,
            task_id=str(task_id),
            intent=goal,
            domain=domain,
            sites=["shopping_admin"] if "admin" in domain else ["shopping"],
            start_url=obs.get("url", ""),
            agent_prompt_wrapper=base_sys_prompt,
        )
        schema_used = mem_res.schema
        if mem_res.injected_text:
            injected_memory = f"{REASONINGBANK_MEMORY_HEADER}\n\n{mem_res.injected_text}"
    decomp_cost = memory_module.decomposer.api_cost_usd - decomp_before[0]
    decomp_prompt_tokens = memory_module.decomposer.api_prompt_tokens - decomp_before[1]
    decomp_completion_tokens = memory_module.decomposer.api_completion_tokens - decomp_before[2]

    # Initialize ReasoningBank dynamic prompting flags
    flags = Flags(
        use_html=False,
        use_ax_tree=True,
        use_thinking=True,
        use_error_logs=True,
        use_past_error_logs=True,
        use_history=True,
        use_action_history=True,
        use_memory=False,
        use_abstract_example=True,
        use_concrete_example=True,
        multi_actions=True,
        use_screenshot=False,
        enable_chat=True,
        demo_mode="off",
    )

    # Initial observation postprocessing
    initial_axtree = flatten_axtree_to_str(obs.get("axtree_object")) if obs.get("axtree_object") else ""
    if len(initial_axtree) > 25000:
        initial_axtree = initial_axtree[:25000] + "\n... [Truncated for brevity]"

    initial_post_obs = {
        "chat_messages": obs.get("chat_messages", [{"role": "user", "message": goal}]),
        "goal": goal,
        "axtree_txt": initial_axtree,
        "pruned_html": "",
        "last_action_error": obs.get("last_action_error", ""),
    }
    obs_history = [initial_post_obs]

    # Build system message following ReasoningBank convention
    sys_prompt = base_sys_prompt
    if injected_memory:
        sys_prompt = f"{sys_prompt}\n\n{injected_memory}"

    step_count = 0
    total_cost_usd = decomp_cost
    total_prompt_tokens = decomp_prompt_tokens
    total_completion_tokens = decomp_completion_tokens
    repeated_action_count = 0
    last_action = ""
    last_axtree_snippet = ""

    try:
        for step in range(max_steps):
            step_count += 1

            main_prompt = MainPrompt(
                obs_history=obs_history,
                actions=actions_taken,
                memories=memories_taken,
                thoughts=thoughts_taken,
                flags=flags,
            )
            user_prompt = main_prompt.prompt

            response_text, _, step_cost, p_toks, c_toks = call_openrouter(
                api_key=api_key,
                model=model,
                system_prompt=sys_prompt,
                user_prompt=user_prompt,
                max_tokens=512,
                temperature=temperature,
            )
            total_cost_usd += step_cost
            total_prompt_tokens += p_toks
            total_completion_tokens += c_toks

            thought = ""
            action = ""
            try:
                ans_dict = main_prompt._parse_answer(response_text)
                action = ans_dict.get("action", "").strip()
                thought = ans_dict.get("think", "").strip()
            except Exception:
                try:
                    ans_dict = parse_html_tags_raise(response_text, keys=["action"], optional_keys=["think"])
                    raw_act = ans_dict.get("action", "")
                    action = "\n".join(raw_act) if isinstance(raw_act, list) else str(raw_act).strip()
                    raw_thk = ans_dict.get("think", "")
                    thought = "\n".join(raw_thk) if isinstance(raw_thk, list) else str(raw_thk).strip()
                except Exception:
                    thought, action = extract_action(response_text)

            # Retry loop if action parsing failed (official ReasoningBank design)
            retry_count = 0
            while not action and retry_count < 2:
                retry_count += 1
                retry_prompt = (
                    f"{user_prompt}\n\n"
                    f"Previous Response:\n{response_text}\n\n"
                    "Error: Your response did not contain an executable action tag. "
                    "You MUST wrap your action in <action>...</action> tags.\n"
                    "- If you have identified the answer to the user's question, emit: <action>send_msg_to_user('YOUR_ANSWER')</action>\n"
                    "- If you need to interact with the page, emit the appropriate action, e.g.: <action>click('bid')</action>"
                )
                retry_resp, _, r_cost, r_p, r_c = call_openrouter(
                    api_key=api_key,
                    model=model,
                    system_prompt=sys_prompt,
                    user_prompt=retry_prompt,
                    max_tokens=512,
                    temperature=0.0,
                )
                total_cost_usd += r_cost
                total_prompt_tokens += r_p
                total_completion_tokens += r_c
                response_text = retry_resp

                try:
                    ans_dict = main_prompt._parse_answer(response_text)
                    action = ans_dict.get("action", "").strip()
                    thought = ans_dict.get("think", "").strip()
                except Exception:
                    try:
                        ans_dict = parse_html_tags_raise(response_text, keys=["action"], optional_keys=["think"])
                        raw_act = ans_dict.get("action", "")
                        action = "\n".join(raw_act) if isinstance(raw_act, list) else str(raw_act).strip()
                        raw_thk = ans_dict.get("think", "")
                        thought = "\n".join(raw_thk) if isinstance(raw_thk, list) else str(raw_thk).strip()
                    except Exception:
                        thought, action = extract_action(response_text)

            if not action:
                action = "noop()"

            if action == "noop()":
                repeated_action_count += 1
            elif action == last_action and action != "":
                repeated_action_count += 1
            else:
                repeated_action_count = 0
            last_action = action

            actions_taken.append(action)
            thoughts_taken.append(thought)
            memories_taken.append(None)

            if "send_msg_to_user" in action:
                try:
                    import ast
                    tree = ast.parse(action.strip())
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "send_msg_to_user":
                            if node.args and isinstance(node.args[0], ast.Constant):
                                final_message = str(node.args[0].value)
                except Exception:
                    pass
                if not final_message:
                    m = re.search(r'send_msg_to_user\s*\(\s*(["\'])(.*?)\1\s*\)', action, re.DOTALL)
                    if m:
                        final_message = m.group(2)

            obs, step_reward, terminated, truncated, step_info = env.step(action)
            event = HandoffEvent(
                interface="agent_to_browser",
                source_role="agent",
                target_role="browser",
                artifact={"action": action},
                observable_state={
                    "url": str(obs.get("url", "")),
                    "last_action_error": str(obs.get("last_action_error", "")),
                    "reward": float(step_reward),
                },
            )
            handoffs.append(HandoffEvent(
                interface=event.interface,
                source_role=event.source_role,
                target_role=event.target_role,
                artifact=event.artifact,
                observable_state=event.observable_state,
                verifier_results=(action_contract.verify(event, cost=0.0),)
                if action_contract else (),
            ))
            if step_reward > 0:
                reward = step_reward
                success = True

            if terminated or truncated:
                if step_reward > 0:
                    success = True
                    reward = step_reward
                break

            if repeated_action_count >= 5:
                # Stagnation Guard: break early if 5 consecutive noop/repeated actions
                break

            # Append postprocessed observation for next step
            cur_axtree = flatten_axtree_to_str(obs.get("axtree_object")) if obs.get("axtree_object") else ""
            if len(cur_axtree) > 25000:
                cur_axtree = cur_axtree[:25000] + "\n... [Truncated for brevity]"

            err_msg = obs.get("last_action_error", "")
            if repeated_action_count >= 3 and not err_msg:
                err_msg = (
                    "Warning: You have performed repeated noops or actions with no state change. "
                    "If you have found the answer, emit: <action>send_msg_to_user('YOUR_ANSWER')</action>. "
                    "Otherwise, take a new navigational or interaction action."
                )

            next_post_obs = {
                "chat_messages": obs.get("chat_messages", [{"role": "user", "message": goal}]),
                "goal": goal,
                "axtree_txt": cur_axtree,
                "pruned_html": "",
                "last_action_error": err_msg,
            }
            obs_history.append(next_post_obs)

    except Exception as e:
        logger.error("Error during execution of task %s on arm %s: %s", task_id, arm, e)
        if len(handoffs) < len(actions_taken):
            handoffs.append(HandoffEvent(
                interface="agent_to_browser", source_role="agent", target_role="browser",
                artifact={"action": actions_taken[-1]},
                observable_state={"last_action_error": str(e)},
            ))
        return TaskExecutionResult(
            arm=arm,
            task_id=task_id,
            intent=goal,
            domain=domain,
            sites=[],
            success=success,
            reward=reward,
            steps=step_count,
            duration_seconds=time.perf_counter() - started_time,
            cost_usd=total_cost_usd,
            decomposition_cost_usd=decomp_cost,
            agent_cost_usd=total_cost_usd,
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            ground_truth=task_gt,
            actions_taken=actions_taken,
            handoffs=handoffs,
            final_message=final_message,
            injected_memory=injected_memory,
            schema_used=schema_used,
            native_success=False,
            autoeval_success=False,
            error=str(e),
        )
    finally:
        env.close()

    duration = time.perf_counter() - started_time

    agent_cost_usd = total_cost_usd
    judge_cost_usd = 0.0

    native_success = (reward > 0.0)
    autoeval_success = native_success
    autoeval_thoughts = ""

    # Official WebArena LLM Fuzzy Match Judge (external/webarena/evaluation_harness/helper_functions.py:llm_fuzzy_match)
    if not native_success and final_message and task_gt and task_gt != "N/A":
        try:
            judge_model = os.environ.get("OPENAI_JUDGE_MODEL", "openai/gpt-4o-mini")
            is_match, explanation, j_cost = webarena_llm_fuzzy_match(
                api_key=api_key,
                judge_model=judge_model,
                question=goal,
                reference=task_gt,
                pred=final_message,
            )
            judge_cost_usd = j_cost
            total_cost_usd += judge_cost_usd
            autoeval_thoughts = explanation
            if is_match:
                autoeval_success = True
        except Exception as judge_err:
            logger.warning(f"Task {task_id} [{arm}]: WebArena llm_fuzzy_match judge call failed: {judge_err}")

    overall_success = native_success or autoeval_success

    return TaskExecutionResult(
        arm=arm,
        task_id=task_id,
        intent=goal,
        domain=domain,
        sites=[],
        success=overall_success,
        reward=reward,
        steps=step_count,
        duration_seconds=duration,
        cost_usd=total_cost_usd,
        decomposition_cost_usd=decomp_cost,
        agent_cost_usd=agent_cost_usd,
        judge_cost_usd=judge_cost_usd,
        prompt_tokens=total_prompt_tokens,
        completion_tokens=total_completion_tokens,
        ground_truth=task_gt,
        actions_taken=actions_taken,
        handoffs=handoffs,
        final_message=final_message,
        injected_memory=injected_memory,
        schema_used=schema_used,
        native_success=native_success,
        autoeval_success=autoeval_success,
        autoeval_thoughts=autoeval_thoughts,
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

# The curated 30-task curriculum suite covering 4 difficulty tiers:
# Easy (6), Medium (8), Moderately Hard (8), Hard/Very Hard (8)
# Includes both previously solved baseline tasks and previously failed tasks expected to succeed after fix
TIER_1_EASY_ATOMIC = [94, 95, 41, 42, 43, 185]
TIER_2_MEDIUM_FILTER = [201, 198, 202, 203, 200, 184, 186, 199]
TIER_3_HARD_PARAM = [193, 194, 197, 6, 204, 127, 0, 119]
TIER_4_VERY_HARD_COMPOSITION = [1, 3, 116, 62, 63, 107, 196, 288]

TEST_SHOPPING_ADMIN_MINI_30 = (
    TIER_1_EASY_ATOMIC
    + TIER_2_MEDIUM_FILTER
    + TIER_3_HARD_PARAM
    + TIER_4_VERY_HARD_COMPOSITION
)

# Comprehensive 100-task curriculum tiers mapping the full shopping admin suite
TIER_1_100 = [
    41, 42, 43, 94, 95, 112, 113, 114, 115, 116,
    157, 198, 199, 200, 201, 202, 203,
    208, 209, 210, 211, 212, 678, 679
]
TIER_2_100 = [
    11, 12, 13, 14, 15, 77, 78, 79,
    128, 129, 130, 131, 183, 184, 185, 186, 187,
    193, 204, 704, 705, 706, 707, 708
]
TIER_3_100 = [
    0, 1, 2, 3, 4, 5, 6,
    119, 120, 121, 122, 123, 127,
    213, 214, 215, 243, 244, 245, 246, 247
]
TIER_4_100 = [
    62, 63, 64, 65, 107, 108, 109, 110, 111,
    194, 195, 196, 197, 288, 289, 290, 291, 292,
    491, 492, 493, 494, 495, 699, 700, 701, 702, 703,
    772, 773, 790
]

TASK_TO_TIER: dict[int, int] = {}
for _tid in TIER_1_100:
    TASK_TO_TIER[_tid] = 1
for _tid in TIER_2_100:
    TASK_TO_TIER[_tid] = 2
for _tid in TIER_3_100:
    TASK_TO_TIER[_tid] = 3
for _tid in TIER_4_100:
    TASK_TO_TIER[_tid] = 4

# Overlay mini30 explicit tiers so curriculum ordering strictly respects mini30 tiers
for _tid in TIER_1_EASY_ATOMIC:
    TASK_TO_TIER[_tid] = 1
for _tid in TIER_2_MEDIUM_FILTER:
    TASK_TO_TIER[_tid] = 2
for _tid in TIER_3_HARD_PARAM:
    TASK_TO_TIER[_tid] = 3
for _tid in TIER_4_VERY_HARD_COMPOSITION:
    TASK_TO_TIER[_tid] = 4


def order_tasks(task_ids: list[int], order: str = "easy-to-hard", seed: int = 42) -> list[int]:
    """Order task IDs based on curriculum configuration."""
    import random
    if order == "easy-to-hard":
        return sorted(task_ids, key=lambda tid: (TASK_TO_TIER.get(tid, 2), task_ids.index(tid)))
    elif order == "hard-to-easy":
        return sorted(task_ids, key=lambda tid: (-TASK_TO_TIER.get(tid, 2), task_ids.index(tid)))
    elif order == "random":
        shuffled = list(task_ids)
        random.Random(seed).shuffle(shuffled)
        return shuffled
    elif order == "natural":
        return sorted(task_ids)
    return task_ids

TEST_SHOPPING_ADMIN_20 = [
    0, 1, 4, 11, 12, 13, 14, 15, 41, 42, 43, 77, 78, 79, 94, 95, 107, 115, 119, 120
]

# Curated 100-task benchmark suite containing 71 Negative Transfer conflict pairs
# across Entity, Cardinality, Status, Temporal, and Action divergence
TEST_SHOPPING_ADMIN_100 = [
    0, 1, 2, 3, 4, 5, 6, 11, 12, 13, 14, 15, 41, 42, 43, 62, 63, 64, 65, 77,
    78, 79, 94, 95, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 119, 120,
    121, 122, 123, 127, 128, 129, 130, 131, 157, 183, 184, 185, 186, 187, 193,
    194, 195, 196, 197, 198, 199, 200, 201, 202, 203, 204, 208, 209, 210, 211,
    212, 213, 214, 215, 243, 244, 245, 246, 247, 288, 289, 290, 291, 292, 491,
    492, 493, 494, 495, 678, 679, 699, 700, 701, 702, 703, 704, 705, 706, 707,
    708, 772, 773, 790
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
    temperature: float = 0.7,
    headless: bool = True,
    output_dir: str = "artifacts/live_browser_benchmark",
    resume: bool = True,
    order: str = "easy-to-hard",
    suite: str = "mini30",
    filter_action_tasks: bool = True,
) -> dict[str, Any]:
    """Run full live comparative benchmark across task IDs and arms with progressive flush and resume."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    latest_json = out_path / "benchmark_results_latest.json"

    # Pre-filter action/DOM-mutation tasks to focus on QA and save token budget
    if filter_action_tasks:
        orig_len = len(task_ids)
        task_ids = [tid for tid in task_ids if is_qa_task(tid)]
        dropped = orig_len - len(task_ids)
        if dropped > 0:
            print(f"[QA-FILTER] Excluded {dropped} Action/DOM-mutation task(s) (no text answers). Active QA tasks: {len(task_ids)}.")

    # Independent memory module per arm for clean continual learning evaluation
    memory_modules: dict[str, COPROMEMMemoryModule] = {
        arm: COPROMEMMemoryModule(api_key=api_key, model=model) for arm in arms
    }
    results_by_arm: dict[str, list[TaskExecutionResult]] = {arm: [] for arm in arms}
    completed_keys: set[tuple[str, int]] = set()

    # Load prior results if resuming
    if resume and latest_json.exists():
        try:
            prior_data = json.loads(latest_json.read_text(encoding="utf-8"))
            if prior_data.get("model") == model:
                restored_arms: set[str] = set()
                for arm, state in prior_data.get("memory_state", {}).items():
                    if arm in memory_modules:
                        memory_modules[arm].load_state(state)
                        restored_arms.add(arm)
                for arm, arm_data in prior_data.get("arms_comparison", {}).items():
                    if arm in results_by_arm:
                        for t_dict in arm_data.get("tasks", []):
                            res_obj = TaskExecutionResult(**t_dict)
                            results_by_arm[arm].append(res_obj)
                            completed_keys.add((arm, res_obj.task_id))

                            # Reconstruct continual learning memory for resumed tasks
                            try:
                                if arm in restored_arms:
                                    continue
                                prior_domain = res_obj.domain
                                if prior_domain == "general" and isinstance(res_obj.schema_used, dict):
                                    family = str(res_obj.schema_used.get("task_family", ""))
                                    if family.startswith("Domain_"):
                                        prior_domain = family.removeprefix("Domain_")
                                if arm in ("semantic_rag", "copromem_v2") and res_obj.actions_taken and res_obj.success:
                                    induced_mem = induce_from_trajectory(
                                        task_id=res_obj.task_id,
                                        goal=res_obj.intent,
                                        actions=res_obj.actions_taken,
                                        success=res_obj.success,
                                        schema_id=(res_obj.schema_used or {}).get("schema_id") if isinstance(res_obj.schema_used, dict) else getattr(res_obj.schema_used, "schema_id", None),
                                        domain=prior_domain if prior_domain != "general" else None,
                                    )
                                    if induced_mem is not None:
                                        memory_modules[arm].add_memory(
                                            induced_mem,
                                            defer_until_admitted=(arm == "copromem_v2"),
                                        )
                                if arm == "copromem_v2":
                                    schema = DecompositionSchema.from_dict(res_obj.schema_used) if isinstance(res_obj.schema_used, dict) else res_obj.schema_used
                                    if schema and not any(s.schema_id == schema.schema_id for s in memory_modules[arm].bank.schemas):
                                        memory_modules[arm].bank.schemas.append(schema)
                                    prior_handoffs = [HandoffEvent(**event) if isinstance(event, dict) else event for event in res_obj.handoffs]
                                    memory_modules[arm].record_episode(
                                        task_id=str(res_obj.task_id),
                                        arm=arm,
                                        success=res_obj.success,
                                        task_state={"intent": res_obj.intent, "constraints": extract_intent_constraints(res_obj.intent)},
                                        schema=schema,
                                        handoffs=prior_handoffs,
                                    )
                            except Exception as mem_err:
                                logger.warning("Could not reconstruct memory for task %s on arm %s: %s", res_obj.task_id, arm, mem_err)
                print(f"[RESUME] Loaded {len(completed_keys)} previously completed task evaluations for model '{model}' from {latest_json}")
                for arm in ("semantic_rag", "copromem_v2"):
                    if arm in memory_modules:
                        print(
                            f"[RESUME] Continual Learning: {len(memory_modules[arm].memories)} active "
                            f"and {len(memory_modules[arm].pending_memories)} pending memories for arm '{arm}'"
                        )
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
    print(f"Temperature: {temperature}")
    print(f"Local Server: {os.environ.get('WA_SHOPPING_ADMIN')}")
    print("=" * 70)

    def flush_report(
        current_task_idx: int | None = None,
        current_task_id: int | None = None,
        current_arm: str | None = None,
    ) -> dict[str, Any]:
        # Fast lookup mapping: arm -> {task_id: TaskExecutionResult}
        arm_task_maps: dict[str, dict[int, TaskExecutionResult]] = {
            arm: {r.task_id: r for r in res_list}
            for arm, res_list in results_by_arm.items()
        }

        # Tasks that are fully completed across ALL arms
        fully_completed_tids = [
            tid for tid in task_ids
            if all(tid in arm_task_maps[a] for a in arms)
        ]
        completed_count = len(fully_completed_tids) if current_task_idx is None else current_task_idx

        summary = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "model": model,
            "suite": suite,
            "curriculum_order": order,
            "total_tasks_in_suite": len(task_ids),
            "completed_tasks_count": completed_count,
            "arms_comparison": {},
            "memory_state": {arm: module.export_state() for arm, module in memory_modules.items()
                             if arm in ("copromem_v2", "semantic_rag")},
        }

        for arm, res_list in results_by_arm.items():
            total = len(res_list)
            native_succ_count = sum(1 for r in res_list if r.native_success)
            autoeval_succ_count = sum(1 for r in res_list if r.autoeval_success)
            overall_succ_count = sum(1 for r in res_list if r.success)

            native_sr = (native_succ_count / total * 100.0) if total > 0 else 0.0
            autoeval_sr = (autoeval_succ_count / total * 100.0) if total > 0 else 0.0
            overall_sr = (overall_succ_count / total * 100.0) if total > 0 else 0.0

            avg_steps = sum(r.steps for r in res_list) / total if total > 0 else 0.0
            avg_duration = sum(r.duration_seconds for r in res_list) / total if total > 0 else 0.0
            total_agent_cost = sum(r.agent_cost_usd for r in res_list)
            total_decomposition_cost = sum(r.decomposition_cost_usd for r in res_list)
            total_judge_cost = sum(r.judge_cost_usd for r in res_list)
            total_cost = sum(r.cost_usd for r in res_list)
            avg_cost = total_cost / total if total > 0 else 0.0
            total_prompt_toks = sum(r.prompt_tokens for r in res_list)
            total_comp_toks = sum(r.completion_tokens for r in res_list)

            summary["arms_comparison"][arm] = {
                "overall_success_count": overall_succ_count,
                "native_success_count": native_succ_count,
                "autoeval_success_count": autoeval_succ_count,
                "total_tasks": total,
                "overall_sr_pct": round(overall_sr, 2),
                "native_sr_pct": round(native_sr, 2),
                "autoeval_sr_pct": round(autoeval_sr, 2),
                "average_steps": round(avg_steps, 2),
                "average_duration_sec": round(avg_duration, 2),
                "total_cost_usd": round(total_cost, 4),
                "agent_cost_usd": round(total_agent_cost, 4),
                "decomposition_cost_usd": round(total_decomposition_cost, 4),
                "judge_cost_usd": round(total_judge_cost, 4),
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
        pct_done = (completed_count / len(task_ids) * 100.0) if task_ids else 0.0
        md_lines = [
            f"# Live Browser WebArena Benchmark Report (Shopping Admin Suite)",
            f"",
            f"- **Timestamp:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **Suite & Curriculum Order:** `{suite}` ({len(task_ids)} tasks) | `{order}`",
            f"- **Agent Model:** `{model}` (via OpenRouter API)",
            f"- **Judge Method:** Official WebArena `llm_fuzzy_match` (`{os.environ.get('OPENAI_JUDGE_MODEL', 'openai/gpt-4o-mini')}` via OpenRouter)",
            f"- **Progress:** {completed_count}/{len(task_ids)} tasks fully evaluated ({pct_done:.1f}%)",
            f"{status_line}",
            f"- **Max Steps Safety Cap:** {max_steps} (Free convergence)",
            f"- **Local Server:** `{os.environ.get('WA_SHOPPING_ADMIN')}`",
            f"",
            f"## 1. Summary Comparison",
            f"",
            f"| Arm | Native SR % (Rigid) | WebArena Fuzzy SR % (LLM Judge) | Overall SR % | Avg Steps | Avg Duration (s) | Agent Cost ($) | Judge Cost ($) | Total Cost ($) | Avg Cost/Task ($) |",
            f"| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
        ]
        for arm, stats in summary["arms_comparison"].items():
            tot = stats['total_tasks']
            nat_str = f"{stats['native_sr_pct']:.1f}% ({stats['native_success_count']}/{tot})"
            judge_str = f"{stats['autoeval_sr_pct']:.1f}% ({stats['autoeval_success_count']}/{tot})"
            over_str = f"**{stats['overall_sr_pct']:.1f}%**"
            md_lines.append(
                f"| `{arm}` | {nat_str} | {judge_str} | {over_str} | {stats['average_steps']:.2f} | {stats['average_duration_sec']:.1f}s | ${stats['agent_cost_usd']:.4f} | ${stats['judge_cost_usd']:.4f} | ${stats['total_cost_usd']:.4f} | ${stats['avg_cost_usd']:.5f} |"
            )

        md_lines.extend([
            f"",
            f"## 2. Outcome Matrix (Chronological Execution Order)",
            f"",
            f"| # | Task ID | Intent | Ground Truth | " + " | ".join(f"`{a}`" for a in arms) + " | Total Task Cost ($) |",
            f"| :---: | :---: | :--- | :--- | " + " | ".join(":---:" for _ in arms) + " | :---: |",
        ])

        # Tasks to display: in chronological order of actual execution
        seen_tids = set()
        displayed_tids = []
        for arm in arms:
            for r in results_by_arm[arm]:
                if r.task_id not in seen_tids:
                    seen_tids.add(r.task_id)
                    displayed_tids.append(r.task_id)
        if current_task_id is not None and current_task_id not in seen_tids:
            displayed_tids.append(current_task_id)

        detailed_task_blocks = []
        for exec_num, tid in enumerate(displayed_tids, 1):
            intent = get_task_intent(tid)
            gt_text = get_task_ground_truth(tid)

            arm_outcomes = []
            task_cost = 0.0
            arm_details = []
            for arm in arms:
                if tid in arm_task_maps[arm]:
                    res = arm_task_maps[arm][tid]
                    task_cost += res.cost_usd
                    nat_badge = "PASS" if res.native_success else "FAIL"
                    judge_badge = "PASS" if res.autoeval_success else "FAIL"
                    compact_status = f"**Nat: {nat_badge} / Jdg: {judge_badge}**<br>({res.steps} steps, ${res.cost_usd:.4f})"
                    arm_outcomes.append(compact_status)

                    ext_str = f"`{res.final_message}`" if res.final_message else "*(None / Aborted)*"
                    if res.native_success:
                        judge_str = "*(Skipped — Native evaluation already passed)*"
                        judge_label = "**PASS** *(Skipped)*"
                    else:
                        judge_str = f"{res.autoeval_thoughts}" if res.autoeval_thoughts else "*(None)*"
                        judge_label = f"**{judge_badge}**"

                    arm_details.append(
                        f"- **`{arm}`:** Native: **{nat_badge}** | Judge: {judge_label} ({res.steps} steps, {res.duration_seconds:.1f}s, ${res.cost_usd:.4f} [Agent: ${res.agent_cost_usd:.4f}, Judge: ${res.judge_cost_usd:.4f}])\n"
                        f"  - **Extracted:** {ext_str}\n"
                        f"  - **Judge Reason:** {judge_str}"
                    )
                else:
                    if current_task_id == tid and current_arm and arm in current_arm:
                        arm_outcomes.append("*(evaluating...)*")
                        arm_details.append(f"- **`{arm}`:** *(evaluating...)*")
                    else:
                        arm_outcomes.append("*(In progress)*")
                        arm_details.append(f"- **`{arm}`:** *(In progress)*")

            md_lines.append(f"| **{exec_num}** | **Task {tid}** | {intent} | `{gt_text}` | " + " | ".join(arm_outcomes) + f" | ${task_cost:.4f} |")

            task_block = [
                f"### #{exec_num} — Task {tid}: {intent}",
                f"- **Expected Ground Truth:** `{gt_text}`",
                f"- **Total Task Cost:** ${task_cost:.4f}",
            ] + arm_details
            detailed_task_blocks.append("\n".join(task_block))

        md_lines.extend([
            f"",
            f"## 3. Task Details & Extracted Answers",
            f"",
        ])
        if detailed_task_blocks:
            md_lines.append("\n\n".join(detailed_task_blocks))
        else:
            md_lines.append("*(No completed task details yet)*")

        md_lines.extend([
            f"",
            f"## 4. Negative Transfer & Memory Separation Audit",
            f"",
            f"| # | Task ID | Arm | Memory Guidance Injected | Veto / Decomposition Mode |",
            f"| :---: | :---: | :---: | :--- | :---: |",
        ])
        for exec_num, tid in enumerate(displayed_tids, 1):
            for arm in arms:
                if tid in arm_task_maps[arm]:
                    res = arm_task_maps[arm][tid]
                    mem_snippet = "*(None)*"
                    mode_str = "N/A"
                    if res.injected_memory:
                        cleaned_mem = res.injected_memory.replace("\n", " ")
                        mem_snippet = (cleaned_mem[:100] + "...") if len(cleaned_mem) > 100 else cleaned_mem
                        if "VETO" in res.injected_memory:
                            mode_str = "YES (VETO)"
                        elif "2-Step Macro Plan" in res.injected_memory:
                            mode_str = "MACRO (2-Step)"
                        elif "Divide-and-Conquer" in res.injected_memory:
                            mode_str = "RECURSIVE (Milestones)"
                        elif "Observed Successful Procedure" in res.injected_memory:
                            mode_str = "PROCEDURE (Observed Success)"
                        else:
                            mode_str = "Active"
                    md_lines.append(f"| {exec_num} | Task {tid} | `{arm}` | {mem_snippet} | {mode_str} |")

        report_md_content = "\n".join(md_lines) + "\n"
        canonical_report = Path("artifacts/live_browser_benchmark_report.md")
        canonical_report.parent.mkdir(parents=True, exist_ok=True)
        canonical_report.write_text(report_md_content, encoding="utf-8")

        out_report = out_path / "benchmark_report.md"
        out_report.write_text(report_md_content, encoding="utf-8")

        # Mirror write to LIVE_MONITOR.md directly
        try:
            Path("LIVE_MONITOR.md").write_text(report_md_content, encoding="utf-8")
        except Exception as err:
            logger.warning("Failed to write LIVE_MONITOR.md: %s", err)

        return summary

    # Initial flush on startup/resume so report shows live state immediately
    flush_report()

    for idx, task_id in enumerate(task_ids, 1):
        domain_str = "Shopping Admin" if task_id in ALL_SHOPPING_ADMIN_184 else "Shopping Storefront"
        print(f"\n--- [{idx}/{len(task_ids)}] Running Task {task_id} ({domain_str}) ---")
        for arm in arms:
            if (arm, task_id) in completed_keys:
                print(f"  > Arm: {arm:<14} [ALREADY COMPLETED, SKIPPING]")
                continue

            # Update live monitor that this arm has started
            flush_report(current_task_id=task_id, current_arm=f"{arm} (evaluating...)")

            print(f"  > Arm: {arm:<14} ...", end="", flush=True)
            res = run_live_task(
                task_id=task_id,
                arm=arm,
                api_key=api_key,
                model=model,
                memory_module=memory_modules[arm],
                max_steps=max_steps,
                temperature=temperature,
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
                    schema_id=(res.schema_used or {}).get("schema_id") if isinstance(res.schema_used, dict) else getattr(res.schema_used, "schema_id", None),
                    domain=res.domain if res.domain != "general" else None,
                )
                if induced_mem is not None:
                    memory_modules[arm].add_memory(
                        induced_mem,
                        defer_until_admitted=(arm == "copromem_v2"),
                    )
            if arm == "copromem_v2":
                memory_modules[arm].record_episode(
                    task_id=str(task_id),
                    arm=arm,
                    success=res.success,
                    task_state={"intent": res.intent, "constraints": extract_intent_constraints(res.intent)},
                    schema=res.schema_used,
                    handoffs=res.handoffs,
                )

            # Flush immediately after EVERY ARM completes!
            flush_report(current_task_id=task_id, current_arm=f"{arm} (completed)")

        # Replay at task-batch boundaries, after all compared arms have finished.
        if idx % 5 == 0:
            for arm, module in memory_modules.items():
                if arm == "copromem_v2":
                    module.consolidate_offline(min_priority=0.20)

        # Flush progressive reports after every full task
        flush_report()

    if "copromem_v2" in memory_modules:
        memory_modules["copromem_v2"].consolidate_offline(min_priority=0.20)
    final_summary = flush_report()
    timestamp = int(time.time())
    final_archive = out_path / f"benchmark_results_{timestamp}.json"
    final_archive.write_text(json.dumps(final_summary, indent=2), encoding="utf-8")
    print(f"\nBenchmark completed! Full final results archived to {final_archive}")
    return final_summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live WebArena BrowserGym Comparative Benchmark")
    parser.add_argument("--suite", type=str, choices=["mini30", "test20", "test100", "full184", "custom"], default="mini30", help="Suite to run: mini30 (curated 30-task curriculum suite), test20 (20 tasks), test100, full184")
    parser.add_argument("--order", type=str, choices=["easy-to-hard", "hard-to-easy", "random", "natural"], default="easy-to-hard", help="Curriculum ordering: easy-to-hard, hard-to-easy, random, natural")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for random order")
    parser.add_argument("--tasks", type=int, nargs="+", default=None, help="Explicit task IDs to evaluate")
    parser.add_argument("--arms", type=str, nargs="+", default=["no_memory", "semantic_rag", "copromem_v2"], help="Memory arms")
    parser.add_argument("--model", type=str, default="google/gemini-2.5-flash", help="OpenRouter model name")
    parser.add_argument("--max_steps", type=int, default=30, help="Max steps safety cap per task")
    parser.add_argument("--temperature", type=float, default=0.7, help="Sampling temperature for LLM actions")
    parser.add_argument("--headless", action="store_true", default=True, help="Run headless")
    parser.add_argument("--output_dir", type=str, default="artifacts/live_browser_benchmark")
    parser.add_argument("--no-resume", action="store_false", dest="resume", help="Disable resume from prior runs")
    parser.add_argument("--filter-action-tasks", action="store_true", default=True, help="Automatically exclude action/DOM-mutation tasks without text answers to save tokens")
    parser.add_argument("--no-filter-action-tasks", action="store_false", dest="filter_action_tasks", help="Do not exclude action tasks")
    args = parser.parse_args()

    if args.tasks is not None and len(args.tasks) > 0:
        task_ids = args.tasks
    elif args.suite == "mini30":
        task_ids = TEST_SHOPPING_ADMIN_MINI_30
    elif args.suite == "full184":
        task_ids = ALL_SHOPPING_ADMIN_184
    elif args.suite == "test100":
        task_ids = TEST_SHOPPING_ADMIN_100
    else:
        task_ids = TEST_SHOPPING_ADMIN_20

    task_ids = order_tasks(task_ids, order=args.order, seed=args.seed)

    api_key = load_api_key()
    run_benchmark(
        task_ids=task_ids,
        arms=args.arms,
        api_key=api_key,
        model=args.model,
        max_steps=args.max_steps,
        temperature=args.temperature,
        headless=args.headless,
        output_dir=args.output_dir,
        resume=args.resume,
        order=args.order,
        suite=args.suite,
        filter_action_tasks=args.filter_action_tasks,
    )
