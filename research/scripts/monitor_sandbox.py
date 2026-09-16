"""Record one fresh, unprivileged Docker process per monitor/public-input pair."""

from __future__ import annotations

import json
import re
import runpy
import subprocess
import time
import uuid
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, canonical, digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
POLICY = runpy.run_path(str(HERE / "monitor_source_policy.py"))
IMAGE = "sha256:b5f9aaedde041e30fc4ff795ab46d47849cfc72701b9ffc8c8983fdefe36fcf6"
LABEL = "cycle23-monitor-sandbox-v1"
DRIVER_VERSION = "isolated-public-input-monitor-driver-v1"


def driver_source():
    return "\n".join(
        (HERE / name).read_text(encoding="utf-8")
        for name in ("monitor_source_policy.py", "monitor_sandbox_driver.py")
    )


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def parse_candidate(text):
    value = json.loads(text, object_pairs_hook=unique_object)
    if type(value) is not dict or set(value) != {"source", "scope_note"}:
        raise ValueError("candidate schema")
    if not isinstance(value["scope_note"], str) or len(value["scope_note"]) > 4000:
        raise ValueError("candidate scope note")
    validation = POLICY["validate_source"](value["source"])
    return {"candidate": value, "validation": validation}


def command(name, payload, driver):
    return [
        "docker",
        "run",
        "--rm",
        "--interactive",
        "--name",
        name,
        "--label",
        "copromem.research=" + LABEL,
        "--label",
        "copromem.input=" + digest(payload),
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--user",
        "65534:65534",
        "--cpus",
        "1",
        "--memory",
        "128m",
        "--memory-swap",
        "128m",
        "--pids-limit",
        "32",
        "--workdir",
        "/tmp",
        "--entrypoint",
        "/usr/bin/env",
        IMAGE,
        "-i",
        "PATH=/usr/local/bin:/usr/bin:/bin",
        "python",
        "-I",
        "-S",
        "-B",
        "-c",
        driver,
    ]


def clean_owned_container(name, payload):
    inspect_argv = ["docker", "inspect", name]
    checked = subprocess.run(
        inspect_argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
        check=False,
    )
    evidence = {
        "inspect_argv": inspect_argv,
        "inspect_stdout": checked.stdout,
        "inspect_stderr": checked.stderr,
        "inspect_exit_code": checked.returncode,
    }
    if checked.returncode:
        if "No such object" not in checked.stderr:
            raise IntegrityError(
                "sandbox cleanup inspection failed; do not assume terminal"
            )
        return evidence
    objects = json.loads(checked.stdout)
    if len(objects) != 1 or objects[0]["Name"] != "/" + name:
        raise IntegrityError("sandbox cleanup container identity mismatch")
    labels = objects[0]["Config"]["Labels"] or {}
    if labels.get("copromem.research") != LABEL or labels.get(
        "copromem.input"
    ) != digest(payload):
        raise IntegrityError("refusing to terminate unowned container")
    kill_argv = ["docker", "kill", name]
    killed = subprocess.run(
        kill_argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
        check=False,
    )
    evidence.update(
        kill_argv=kill_argv,
        kill_stdout=killed.stdout,
        kill_stderr=killed.stderr,
        kill_exit_code=killed.returncode,
    )
    if (
        killed.returncode
        and "is not running" not in killed.stderr
        and "No such container" not in killed.stderr
    ):
        raise IntegrityError("owned sandbox did not terminate cleanly")
    return evidence


def parse_process(record, payload):
    if record["wall_timeout"]:
        return {
            "status": "wall_timeout",
            "verdict": None,
            "error_type": "HostWallTimeout",
        }
    if record["exit_code"] != 0:
        return {
            "status": "process_failure",
            "verdict": None,
            "error_type": "NonzeroContainerExit",
        }
    if record["stderr"]:
        raise IntegrityError("unexpected sandbox stderr on successful process")
    try:
        value = json.loads(record["stdout"], object_pairs_hook=unique_object)
    except (ValueError, TypeError) as exc:
        raise IntegrityError("sandbox output is not unique valid JSON") from exc
    if (
        type(value) is not dict
        or set(value)
        != {
            "version",
            "source_digest",
            "input_digest",
            "status",
            "verdict",
            "error_type",
        }
        or value["version"] != DRIVER_VERSION
        or value["source_digest"] != digest(payload["source"])
        or value["input_digest"] != digest(payload["input"])
    ):
        raise IntegrityError("sandbox output not bound to registered source/input")
    if value["status"] not in {
        "ok",
        "policy_rejected",
        "invalid_result",
        "cpu_timeout",
        "runtime_error",
    }:
        raise IntegrityError("unknown sandbox status")
    if value["status"] == "ok":
        if (
            type(value["verdict"]) is not bool and value["verdict"] is not None
        ) or value["error_type"] is not None:
            raise IntegrityError("nonboolean accepted sandbox result")
    elif value["verdict"] is not None or not isinstance(value["error_type"], str):
        raise IntegrityError("failed sandbox cannot produce a verdict")
    return value


def run_case(store: RunStore, key: str, source: str, public: dict):
    POLICY["validate_public_input"](public)
    payload = {"source": source, "input": public}
    driver = driver_source()
    binding = {
        "payload_digest": digest(payload),
        "driver_digest": digest(driver),
        "image": IMAGE,
    }
    existing = store.read("sandbox_processes", key)
    if existing is not None:
        attempt = store.read("sandbox_attempts", key)
        if (
            attempt is None
            or not re.fullmatch(r"copromem-c23-[0-9a-f]{20}", attempt["container_name"])
            or attempt["binding"] != binding
            or existing["argv"] != attempt["argv"]
            or attempt["argv"] != command(attempt["container_name"], payload, driver)
            or existing["stdin"] != canonical(payload)
            or existing["cwd"] != str(ROOT)
        ):
            raise IntegrityError("sandbox resume source/input/driver changed")
        return {
            "process_digest": digest(existing),
            "result": parse_process(existing, payload),
        }
    if store.read("sandbox_attempts", key) is not None:
        raise IntegrityError(
            "unresolved sandbox attempt; inspect its live container, do not silently restart"
        )
    name = "copromem-c23-" + uuid.uuid4().hex[:20]
    argv = command(name, payload, driver)
    store.write(
        "sandbox_attempts",
        key,
        {"binding": binding, "container_name": name, "argv": argv},
    )
    started = time.perf_counter()
    try:
        result = subprocess.run(
            argv,
            input=canonical(payload),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
            cwd=ROOT,
            check=False,
        )
        record = {
            "argv": argv,
            "stdin": canonical(payload),
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "wall_timeout": False,
            "cleanup": None,
        }
    except subprocess.TimeoutExpired as exc:

        def decoded(value):
            return (
                value.decode("utf-8", errors="replace")
                if isinstance(value, bytes)
                else value or ""
            )

        partial = {
            "stdout": decoded(exc.stdout),
            "stderr": decoded(exc.stderr),
            "binding": binding,
            "container_name": name,
        }
        store.write("sandbox_timeout_outputs", key, partial)
        record = {
            "argv": argv,
            "stdin": canonical(payload),
            "stdout": partial["stdout"],
            "stderr": partial["stderr"],
            "exit_code": None,
            "wall_timeout": True,
            "cleanup": clean_owned_container(name, payload),
        }
    except OSError as exc:
        store.write(
            "sandbox_launch_failures",
            key,
            {"error_type": type(exc).__name__, "container_name": name},
        )
        raise
    if not record["wall_timeout"] and record["exit_code"] != 0:
        record["cleanup"] = clean_owned_container(name, payload)
    record["cwd"] = str(ROOT)
    record["latency_seconds"] = time.perf_counter() - started
    store.write("sandbox_processes", key, record)
    return {"process_digest": digest(record), "result": parse_process(record, payload)}
