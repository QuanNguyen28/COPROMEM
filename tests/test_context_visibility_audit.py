import importlib.util
from pathlib import Path

import pytest

from copromem.checkpoints import IntegrityError, RunStore, digest
from copromem.stateful_source import prompt_context

spec = importlib.util.spec_from_file_location(
    "context_audit",
    Path(__file__).parents[1] / "research/scripts/audit_context_visibility.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def populate(root):
    store = RunStore(root)
    store.write(
        "protocol", "preregistration", {"cycle_id": "fixture", "context_chars": 5000}
    )
    previous = []
    for index in range(3):
        frame = {
            "task_id": "fixture",
            "public_instruction": "Public task",
            "results": previous.copy(),
            "completion_flag": False,
            "harness_only_state": {"secret": "NEVER_VISIBLE"},
        }
        checkpoint = {"public_context": prompt_context(frame, 5000)}
        checkpoint_id = digest(checkpoint)
        store.write("public_handoffs", checkpoint_id, checkpoint)
        store.write("stream_frames", f"episode-{index:03d}", frame)
        step = {
            "episode_id": "episode",
            "step": index,
            "public_checkpoint_id": checkpoint_id,
            "code": "print('public')",
            "public_output": "x" * 4500,
        }
        store.write("source_steps", f"episode-{index:02d}", step)
        previous.append({"program": step["code"], "output": step["public_output"]})
    return store


def test_context_diagnostics_reproduce_saved_inputs_and_never_label_success(tmp_path):
    populate(tmp_path)
    report = module.audit(tmp_path)
    assert report["totals"]["boundaries"] == 3
    assert report["totals"]["boundaries_omitting_earlier_history"] == 1
    assert report["totals"]["boundaries_with_truncated_visible_entry"] == 2
    assert report["totals"]["exact_consecutive_program_repeat"] == 2
    assert report["totals"]["outputs_exceeding_4000_chars"] == 3
    assert report["model_calls"] == 0
    assert "NEVER_VISIBLE" not in str(report)
    assert "native_success" not in report


def test_context_audit_rejects_missing_boundary(tmp_path):
    store = RunStore(tmp_path)
    store.write(
        "protocol", "preregistration", {"cycle_id": "fixture", "context_chars": 5000}
    )
    store.write("source_steps", "episode-00", {"episode_id": "episode", "step": 0})
    with pytest.raises(IntegrityError, match="missing public boundary"):
        module.audit(tmp_path)
