from __future__ import annotations

import ast
from pathlib import Path

from copromem.experiments.reme_copromem.prompt_memory import render_executor_memory_slot
from copromem.experiments.reme_copromem.runner import _copromem_prompt_memory_text
from copromem.integrations.reasoning_bank.appworld import render_retrieval_guidance


ROOT = Path(__file__).resolve().parents[2]


def _function(path: Path, name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    matches = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == name]
    assert len(matches) == 1
    return matches[0]


def test_historical_renderer_import_is_a_behavior_free_delegate_to_executor_slot_renderer():
    guidance = "line one\nΔ line two"
    assert _copromem_prompt_memory_text(guidance) == render_executor_memory_slot(guidance)
    shim = _function(ROOT / "src/copromem/experiments/reme_copromem/runner.py", "_copromem_prompt_memory_text")
    calls = [node for node in ast.walk(shim) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
    assert [node.func.id for node in calls] == ["render_executor_memory_slot"]
    # The shim may document itself, but must not carry a second template.
    assert not any(isinstance(node, ast.Constant) and isinstance(node.value, str) and "Experience 1:" in node.value
                   for node in ast.walk(shim))


def test_reasoningbank_has_one_guidance_renderer_and_provenance_only_verifies_it():
    appworld = ROOT / "src/copromem/integrations/reasoning_bank/appworld.py"
    lifecycle = (ROOT / "src/copromem/integrations/reasoning_bank/lifecycle.py").read_text(encoding="utf-8")
    provenance = (ROOT / "src/copromem/integrations/reasoning_bank/retrieval_provenance.py").read_text(encoding="utf-8")
    renderer = _function(appworld, "render_retrieval_guidance")
    assert any(isinstance(node, ast.Name) and node.id == "MEMORY_PROMPT" for node in ast.walk(renderer))
    assert "render_retrieval_guidance(result.guidance)" in lifecycle
    assert "render_retrieval_guidance(raw_memory)" in provenance
    assert "def _prompt_memory" not in provenance
    raw = "# Memory Item 1\n## Content raw"
    assert render_retrieval_guidance(raw) != raw


def test_static_renderer_and_raw_memory_return_paths_cannot_fork():
    """Only the authoritative renderer may create executor-visible guidance."""
    root = ROOT / "src/copromem/integrations/reasoning_bank"
    sources = {name: (root / name).read_text(encoding="utf-8")
               for name in ("appworld.py", "lifecycle.py", "retrieval_provenance.py", "dynamic_runtime.py")}
    assert sum(source.count("MEMORY_PROMPT") for source in sources.values()) == 2  # declaration + renderer use
    assert "return result.guidance" not in sources["lifecycle.py"]
    assert "return retrieval.guidance" not in sources["dynamic_runtime.py"]
    assert "def _prompt_memory" not in "\n".join(sources.values())
    # The generic executor slot is a separate, single-purpose wrapper.  It
    # cannot become an alternative ReasoningBank guidance renderer.
    slot = (ROOT / "src/copromem/experiments/reme_copromem/prompt_memory.py").read_text(encoding="utf-8")
    assert "MEMORY_PROMPT" not in slot and "raw_memory" not in slot
