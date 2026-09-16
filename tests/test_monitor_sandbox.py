import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from copromem.checkpoints import IntegrityError, RunStore, canonical, digest

HERE = Path(__file__).parents[1] / "research/scripts"
POLICY = runpy.run_path(str(HERE / "monitor_source_policy.py"))
SANDBOX = runpy.run_path(str(HERE / "monitor_sandbox.py"))
VALID = "def judge(program, present_names):\n    return any(isinstance(n, ast.While) for n in ast.walk(ast.parse(program)))"
PUBLIC = {
    "program": "raise RuntimeError('target is never executed')",
    "present_names": [],
}


def result(source=VALID, public=PUBLIC, verdict=True):
    return {
        "version": SANDBOX["DRIVER_VERSION"],
        "source_digest": digest(source),
        "input_digest": digest(public),
        "status": "ok",
        "verdict": verdict,
        "error_type": None,
    }


def test_host_only_parses_the_proposed_program():
    info = POLICY["validate_source"](VALID)
    assert info["functions"] == ["judge"] and info["node_count"] > 10
    # A source body raising on evaluation is syntax-checked, never called here.
    assert POLICY["validate_source"](
        "def judge(program, present_names):\n    return 1 / 0"
    )


@pytest.mark.parametrize(
    "source",
    [
        "import os\ndef judge(program, present_names): return True",
        "def judge(program, present_names):\n import os\n return True",
        "def judge(program, present_names): return eval(program)",
        "def judge(program, present_names): return program.__class__",
        "def judge(program, present_names): return open('private')",
        "def judge(program, present_names=1): return True",
        "@something\ndef judge(program, present_names): return True",
        "def judge(program: str, present_names): return True",
        "def judge(program, present_names):\n ast.parse = 0\n return True",
        "def judge(program, present_names):\n global x\n return True",
        "def judge(program, present_names):\n try: return True\n except: return False",
        "def judge(program, present_names):\n def nested(): return True\n return nested()",
        "x=1\ndef judge(program, present_names): return True",
    ],
)
def test_policy_rejects_forbidden_constructs(source):
    with pytest.raises(POLICY["PolicyError"]):
        POLICY["validate_source"](source)


def test_complete_strict_candidate_object_and_no_markdown_repair():
    assert SANDBOX["parse_candidate"](
        json.dumps({"source": VALID, "scope_note": "bounded"})
    )["validation"]["functions"] == ["judge"]
    for raw in (
        "```json\n{}\n```",
        '{"source":"x","source":"y","scope_note":"z"}',
        '{"source":"x","scope_note":"y","label":true}',
    ):
        with pytest.raises(ValueError):
            SANDBOX["parse_candidate"](raw)


def test_runtime_input_rejects_labels_and_unordered_or_duplicate_names():
    POLICY["validate_public_input"](PUBLIC)
    for public in (
        {**PUBLIC, "label": True},
        {**PUBLIC, "present_names": ["a", "a"]},
        {**PUBLIC, "present_names": ["b", "a"]},
    ):
        with pytest.raises(POLICY["PolicyError"]):
            POLICY["validate_public_input"](public)


def test_container_command_has_no_host_mount_network_or_secret_environment():
    payload = {"source": VALID, "input": PUBLIC}
    argv = SANDBOX["command"]("copromem-c23-" + "a" * 20, payload, "driver")
    assert argv[argv.index("--network") + 1] == "none"
    assert argv[argv.index("--entrypoint") + 1] == "/usr/bin/env"
    assert argv[argv.index("--user") + 1] == "65534:65534"
    assert "--read-only" in argv and "--mount" not in argv and "--volume" not in argv
    assert (
        "--env" not in argv and "--env-file" not in argv and "--privileged" not in argv
    )
    assert argv[argv.index(SANDBOX["IMAGE"]) + 1] == "-i"
    assert argv[argv.index("--memory") + 1] == "128m"


@pytest.mark.parametrize(
    "change",
    [
        {"source_digest": "wrong"},
        {"input_digest": "wrong"},
        {"verdict": 1},
        {"status": "unrecognized"},
        {"label": True},
    ],
)
def test_output_corruption_or_fake_boolean_is_rejected(change):
    record = {
        "wall_timeout": False,
        "exit_code": 0,
        "stderr": "",
        "stdout": json.dumps({**result(), **change}),
    }
    with pytest.raises(IntegrityError):
        SANDBOX["parse_process"](record, {"source": VALID, "input": PUBLIC})


def test_recorded_process_reuses_only_exact_binding_and_command(monkeypatch):
    store = RunStore()
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        assert json.loads(kwargs["input"]) == {"source": VALID, "input": PUBLIC}
        return SimpleNamespace(
            stdout=canonical(result()) + "\n", stderr="", returncode=0
        )

    monkeypatch.setattr(SANDBOX["subprocess"], "run", fake_run)
    first = SANDBOX["run_case"](store, "fixture", VALID, PUBLIC)
    assert first == SANDBOX["run_case"](store, "fixture", VALID, PUBLIC)
    assert len(calls) == 1
    with pytest.raises(IntegrityError):
        SANDBOX["run_case"](store, "fixture", VALID, {**PUBLIC, "program": "x=2"})


def test_unresolved_attempt_is_not_restarted(monkeypatch):
    store = RunStore()
    store.write("sandbox_attempts", "fixture", {"incomplete": True})
    monkeypatch.setattr(
        SANDBOX["subprocess"], "run", lambda *args, **kwargs: pytest.fail("no restart")
    )
    with pytest.raises(IntegrityError):
        SANDBOX["run_case"](store, "fixture", VALID, PUBLIC)


@pytest.mark.parametrize("raw", ["[]", '{"status":"ok","status":"ok"}', "not-json"])
def test_malformed_or_duplicate_output_is_not_a_verdict(raw):
    record = {"wall_timeout": False, "exit_code": 0, "stderr": "", "stdout": raw}
    with pytest.raises(IntegrityError):
        SANDBOX["parse_process"](record, {"source": VALID, "input": PUBLIC})


def test_cleanup_never_kills_a_container_with_wrong_ownership(monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(
            stdout=json.dumps([{"Name": "/foreign", "Config": {"Labels": {}}}]),
            stderr="",
            returncode=0,
        )

    monkeypatch.setattr(SANDBOX["subprocess"], "run", fake_run)
    with pytest.raises(IntegrityError):
        SANDBOX["clean_owned_container"]("foreign", {"source": VALID, "input": PUBLIC})
    assert len(calls) == 1 and calls[0][:2] == ["docker", "inspect"]
