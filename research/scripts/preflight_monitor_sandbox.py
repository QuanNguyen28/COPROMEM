"""Constructed isolated-runtime fixtures; no learned proposal or native action."""

from __future__ import annotations

import json
import runpy
import subprocess
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SANDBOX = runpy.run_path(str(HERE / "monitor_sandbox.py"))
PUBLIC = {
    "program": "raise RuntimeError('target_not_executed')",
    "present_names": ["available"],
}
FIXTURES = (
    ("ast_analysis", "return isinstance(ast.parse(program), ast.Module)", "ok", True),
    ("name_context", "return 'available' in present_names", "ok", True),
    ("abstention", "return None", "ok", None),
    ("not_boolean", "return 1", "invalid_result", None),
    ("runtime_failure", "return 1 / 0", "runtime_error", None),
    ("private_attribute", "return program.__class__", "policy_rejected", None),
    ("forbidden_import", "import os\n    return True", "policy_rejected", None),
    ("no_module_global_exposure", "return ast.sys is None", "runtime_error", None),
    (
        "immutable_names",
        "present_names.append('new')\n    return True",
        "runtime_error",
        None,
    ),
    ("cpu_bound", "while True:\n        pass", "cpu_timeout", None),
)


def main():
    store = RunStore(ROOT / "artifacts/research/cycle23_monitor_sandbox_preflight")
    inspected = subprocess.run(
        ["docker", "image", "inspect", SANDBOX["IMAGE"]],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=15,
    )
    info = json.loads(inspected.stdout)[0]
    if (
        info["Id"] != SANDBOX["IMAGE"]
        or info["Os"] != "linux"
        or info["Config"].get("Volumes")
    ):
        raise IntegrityError("isolated image identity/OS/implicit-volume check failed")
    profile = {
        "image": info["Id"],
        "os": info["Os"],
        "architecture": info["Architecture"],
        "implicit_volumes": info["Config"].get("Volumes"),
        "image_environment_names": [
            entry.split("=", 1)[0] for entry in info["Config"].get("Env", [])
        ],
        "runtime_environment_cleared": True,
        "entrypoint_overridden": True,
    }
    paths = [
        HERE / name
        for name in (
            "monitor_source_policy.py",
            "monitor_sandbox_driver.py",
            "monitor_sandbox.py",
            "preflight_monitor_sandbox.py",
        )
    ]
    paths.append(ROOT / "tests/test_monitor_sandbox.py")
    texts = {
        p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8") for p in paths
    }
    protocol = {
        "stage": "constructed_monitor_sandbox_preflight",
        "fixtures": FIXTURES,
        "public_input": PUBLIC,
        "source_snapshot": digest(texts),
        "image_profile": profile,
        "model_calls": 0,
        "native_executions": 0,
        "api_usd": 0,
    }
    store.bind_provenance({"protocol_digest": digest(protocol)})
    store.write("protocol", "preregistration", protocol)
    store.write("source_snapshots", digest(texts), texts)
    rows = []
    for name, body, expected_status, expected_verdict in FIXTURES:
        source = "def judge(program, present_names):\n    " + body
        repeated = []
        for repeat in range(2):
            key = f"{name}-{repeat}"
            row = SANDBOX["run_case"](store, key, source, PUBLIC)
            store.write("fixture_results", key, row)
            repeated.append(row)
        passed = (
            all(
                r["result"]["status"] == expected_status
                and r["result"]["verdict"] is expected_verdict
                for r in repeated
            )
            and repeated[0]["result"] == repeated[1]["result"]
        )
        rows.append({"fixture": name, "passed": passed, "results": repeated})
        print(json.dumps({"fixture": name, "passed": passed}), flush=True)
    keys = {f"{name}-{repeat}" for name, *_ in FIXTURES for repeat in range(2)}
    for kind, expected in (
        ("sandbox_attempts", keys),
        ("sandbox_processes", keys),
        ("fixture_results", keys),
        ("calls", set()),
        ("native_evaluation", set()),
    ):
        if {p.stem for p in (store.root / kind).glob("*.json")} != expected:
            raise IntegrityError("sandbox preflight inventory changed")
    report = {
        "protocol_digest": digest(protocol),
        "source_snapshot": digest(texts),
        "rows": rows,
        "fixtures": len(FIXTURES),
        "sandbox_processes": len(keys),
        "all_passed": all(r["passed"] for r in rows),
        "model_calls": 0,
        "native_executions": 0,
        "api_usd": 0,
    }
    store.write("reports", digest(report), report)
    print(
        json.dumps(
            {
                "report_digest": digest(report),
                **{k: v for k, v in report.items() if k != "rows"},
            },
            indent=2,
        )
    )
    if not report["all_passed"]:
        raise IntegrityError(
            "constructed sandbox gate failed; no generated monitor execution"
        )


if __name__ == "__main__":
    main()
