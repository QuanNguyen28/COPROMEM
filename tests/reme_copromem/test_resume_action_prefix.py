from __future__ import annotations

import hashlib

from copromem.experiments.reme_copromem import runner
from copromem.integrations.reme.transport import AppendOnlyLedger


def test_resume_read_only_prefix_rebuilds_history_without_rescoring_prefix(tmp_path, monkeypatch):
    source_codes = ["print('docs')", "print('venmo docs')"]
    outputs = {source_codes[0]: "docs-output", source_codes[1]: "venmo-output", "print('new')": "new-output"}
    worlds = []

    class World:
        def __init__(self, **_kwargs):
            self.task = type("Task", (), {"instruction": "task", "app_descriptions": "apps", "supervisor": "sup"})()
            self.executed = []; worlds.append(self)
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def execute(self, code): self.executed.append(code); return outputs[code]
        def task_completed(self): return False
        def mark_post_trajectory_score(self): pass

    class Agent:
        def __init__(self, **_kwargs):
            self.history = [[[]]]
            self.llm_client = type("Client", (), {"chat": type("Chat", (), {"completions": object()})()})()
        def get_memory(self, _query): return []
        def call_llm(self, _messages): return "print('new')"
        def extract_code_and_fix_content(self, value): return value, value
        def get_reward(self, _world): return 0.5

    monkeypatch.setattr(runner, "AppWorldProxy", World)
    monkeypatch.setattr(runner, "load_official_agent", lambda **_kwargs: Agent)
    monkeypatch.setattr(runner, "configure_memory_transport", lambda *_args: None)
    monkeypatch.setattr(runner, "build_initial_prompt", lambda *_args: [])
    actions = [{"code": code, "code_sha256": hashlib.sha256(code.encode()).hexdigest(),
                "output_sha256": hashlib.sha256(outputs[code].encode()).hexdigest()} for code in source_codes]
    result = runner.execute_trajectory(
        run=tmp_path, progress=tmp_path / "progress.jsonl", ledger=AppendOnlyLedger(tmp_path / "ledger.jsonl", 10),
        api_key="", all_task_ids=["task"], arm="official_upstream_reme_fixed", task_id="task", trial_id=2, seed=2,
        max_actions=3, temperature=.7, artifact_path=tmp_path / "artifact.json",
        resume_actions=actions, resumed_before_score=0.0,
        resume_provenance={"source_journal_sha256": "x"},
    )
    assert result["before_score"] == 0.0
    assert result["after_score"] == 0.5
    assert result["reconstructed_action_count"] == 2
    assert worlds[0].executed == source_codes + ["print('new')"]
    assert result["history"][0]["content"] == source_codes[0]


def test_resume_prefix_rejects_changed_output_before_new_model_call(tmp_path, monkeypatch):
    class World:
        def __init__(self, **_kwargs): self.task = type("Task", (), {"instruction": "task", "app_descriptions": "apps", "supervisor": "sup"})()
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def execute(self, _code): return "changed"
        def task_completed(self): return False
        def mark_post_trajectory_score(self): pass
    class Agent:
        def __init__(self, **_kwargs): self.history = [[[]]]
        def get_memory(self, _query): return []
        def call_llm(self, _messages): raise AssertionError("model must not be called")
    monkeypatch.setattr(runner, "AppWorldProxy", World)
    monkeypatch.setattr(runner, "load_official_agent", lambda **_kwargs: Agent)
    monkeypatch.setattr(runner, "configure_memory_transport", lambda *_args: None)
    monkeypatch.setattr(runner, "build_initial_prompt", lambda *_args: [])
    code = "print('docs')"
    action = {"code": code, "code_sha256": hashlib.sha256(code.encode()).hexdigest(),
              "output_sha256": hashlib.sha256(b"original").hexdigest()}
    import pytest
    with pytest.raises(RuntimeError, match="output differs"):
        runner.execute_trajectory(run=tmp_path, progress=tmp_path / "progress.jsonl",
            ledger=AppendOnlyLedger(tmp_path / "ledger.jsonl", 10), api_key="", all_task_ids=["task"],
            arm="official_upstream_reme_fixed", task_id="task", trial_id=2, seed=2, max_actions=3, temperature=.7,
            resume_actions=[action], resumed_before_score=0.0, resume_provenance={"source_journal_sha256": "x"})
