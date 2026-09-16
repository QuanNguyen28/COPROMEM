"""Offline official ExpeL CLI/rule-update probes in an isolated environment."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from copromem.checkpoints import RunStore, digest

IMAGE = "sha256:e1ba9148ebb3c963ad8efcd468a0b80a809d133776bb85e8bc11af0312a39ce5"
RUNTIME_ENV = ["ALFWORLD_DATA=/tmp/alfworld", "XDG_CACHE_HOME=/tmp/cache"]
FIXTURE = """
import json
from copy import deepcopy
from agent.expel import parse_rules, update_rules

checks = []
ops = parse_rules('ADD: Check observed fields.\\nAGREE 1: Check observed fields.')
assert ops == [('ADD', 'Check observed fields.'), ('AGREE 1', 'Check observed fields.')]
checks.append('native parser preserves valid period-terminated operations')
assert parse_rules('ADD: missing period') == []
checks.append('isolated unfinished rule is rejected')
malformed = parse_rules('ADD: Check observed fields.\\nADD: missing period\\nAGREE 1: Check observed fields.')
assert malformed == [('ADD', 'Check observed fields.'), ('ADD', 'Check observed fields.')]
checks.append('recorded native multiline regex quirk: unfinished ADD absorbs following AGREE')
initial = [('Check observed fields.', 2), ('Avoid repeated failures.', 1)]
updated = update_rules(deepcopy(initial), [('REMOVE 2', 'Avoid repeated failures.'), ('AGREE 1', 'Check observed fields.'), ('ADD', 'Use observed values.')])
assert updated == [('Check observed fields.', 3), ('Use observed values.', 2)]
checks.append('native add/agree/remove counters and sorting')
assert update_rules(deepcopy(initial), [('REMOVE 1', 'Check observed fields.')], list_full=True) == [('Avoid repeated failures.', 1)]
checks.append('native full-bank removal has stronger decrement')
assert update_rules(deepcopy(initial), [('ADD', 'Check observed fields.')]) == initial
checks.append('native duplicate addition does not create a new rule')
print(json.dumps({'passed': len(checks), 'checks': checks, 'source': 'unmodified agent.expel functions', 'kind': 'authored fixture, not learned performance'}))
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default=IMAGE)
    parser.add_argument("--embedding-manifest")
    parser.add_argument("--alfworld-manifest")
    args = parser.parse_args()
    if args.embedding_manifest and args.alfworld_manifest:
        parser.error("choose one independent native probe mode")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.image):
        parser.error("an immutable Docker image ID is required")
    image = args.image
    root = Path(__file__).resolve().parents[2]
    vendor = root / "vendor/ExpeL"
    store = RunStore(root / "artifacts/research/expel_native_probe_20260916")
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=vendor, text=True
    ).strip()
    source = {
        str(path.relative_to(vendor)): digest(path.read_text(encoding="utf-8"))
        for path in vendor.rglob("*.py")
    }
    store.write(
        "native_source_provenance",
        digest(source),
        {"revision": revision, "source_hashes": source},
    )
    store.write("authored_fixtures", digest(FIXTURE), {"code": FIXTURE})
    commands = [
        ("train-help", ["train.py", "--help"], None),
        ("insight-help", ["insight_extraction.py", "--help"], None),
        ("eval-help", ["eval.py", "--help"], None),
        ("rule-update", ["-"], FIXTURE),
        ("dependency-check", ["-m", "pip", "check"], None),
        (
            "environment",
            [
                "-c",
                "import json,platform; from pathlib import Path; print(json.dumps({'python':platform.python_version(),'install_reports':{p.name:json.loads(p.read_text()) for p in sorted(Path('/opt').glob('*install.json'))}}))",
            ],
            None,
        ),
    ]
    mounts = ["--mount", f"type=bind,source={vendor},target=/vendor,readonly"]
    runtime_env = list(RUNTIME_ENV)
    limits = {"cpus": "1", "memory": "1g", "tmpfs": "128m", "timeout": 45}
    embedding_manifest = None
    alfworld_manifest = None
    if args.embedding_manifest:
        if not re.fullmatch(r"[0-9a-f]{64}", args.embedding_manifest):
            parser.error("an immutable embedding manifest ID is required")
        embedding_manifest = store.read("embedding_models", args.embedding_manifest)
        if (
            embedding_manifest is None
            or digest(embedding_manifest) != args.embedding_manifest
        ):
            parser.error("embedding manifest is absent or corrupted")
        model_dir = Path(embedding_manifest["model_directory"]).resolve()
        if not model_dir.is_relative_to((store.root / "models").resolve()):
            parser.error("model directory is outside the research model store")
        for name, entry in embedding_manifest["files"].items():
            path = (model_dir / name).resolve()
            if not path.is_relative_to(model_dir):
                parser.error("model manifest contains a path outside its directory")
            with path.open("rb") as stream:
                observed = hashlib.file_digest(stream, "sha256").hexdigest()
            if observed != entry["sha256"] or path.stat().st_size != entry["bytes"]:
                parser.error("model file integrity check failed")
        # No extra artifacts, remote code, or pickle can enter the read-only mount.
        if {
            str(p.relative_to(model_dir)).replace("\\", "/")
            for p in model_dir.rglob("*")
            if p.is_file()
        } != set(embedding_manifest["files"]):
            parser.error("unexpected file in embedding directory")
        fixture = (root / "research/fixtures/expel_native_retrieval.py").read_text(
            encoding="utf-8"
        )
        store.write("authored_fixtures", digest(fixture), {"code": fixture})
        commands = [("native-retrieval", ["-"], fixture)]
        mounts += ["--mount", f"type=bind,source={model_dir},target=/model,readonly"]
        runtime_env += [
            "HF_HUB_OFFLINE=1",
            "TRANSFORMERS_OFFLINE=1",
            "HF_DATASETS_OFFLINE=1",
            "TOKENIZERS_PARALLELISM=false",
            "OMP_NUM_THREADS=2",
        ]
        limits = {"cpus": "2", "memory": "2g", "tmpfs": "256m", "timeout": 120}
    if args.alfworld_manifest:
        if not re.fullmatch(r"[0-9a-f]{64}", args.alfworld_manifest):
            parser.error("an immutable ALFWorld manifest ID is required")
        data_store = RunStore(
            root / "artifacts/research/alfworld_native_probe_20260916"
        )
        alfworld_manifest = data_store.read("data_manifests", args.alfworld_manifest)
        if (
            alfworld_manifest is None
            or digest(alfworld_manifest) != args.alfworld_manifest
        ):
            parser.error("ALFWorld data manifest is missing or corrupted")
        data_dir = Path(alfworld_manifest["data_directory"]).resolve()
        if data_dir != (data_store.root / "selected_data").resolve():
            parser.error("unexpected ALFWorld data directory")
        expected_files = {
            **alfworld_manifest["files"],
            **{
                "logic/" + name: entry
                for name, entry in alfworld_manifest["logic"].items()
            },
        }
        for name, entry in expected_files.items():
            path = (data_dir / name).resolve()
            if not path.is_relative_to(data_dir):
                parser.error("unsafe ALFWorld manifest path")
            with path.open("rb") as stream:
                observed = hashlib.file_digest(stream, "sha256").hexdigest()
            if observed != entry["sha256"] or path.stat().st_size != entry["bytes"]:
                parser.error("ALFWorld data integrity failed")
        if {
            p.relative_to(data_dir).as_posix()
            for p in data_dir.rglob("*")
            if p.is_file()
        } != set(expected_files):
            parser.error("unexpected file in selected native dataset")
        selected = alfworld_manifest["selection"]["selected_directory"]
        if not selected.startswith("json_2.1.1/train/"):
            parser.error("native fixture must be train-only")
        fixture = (root / "research/fixtures/expel_alfworld_native.py").read_text(
            encoding="utf-8"
        )
        store.write("authored_fixtures", digest(fixture), {"code": fixture})
        commands = [
            ("alfworld-native-0", ["-"], fixture),
            ("alfworld-native-1", ["-"], fixture),
        ]
        mounts += ["--mount", f"type=bind,source={data_dir},target=/dataset,readonly"]
        runtime_env += [
            "ALFWORLD_FIXTURE_GAMEFILE=/dataset/" + selected + "/game.tw-pddl",
            "OMP_NUM_THREADS=2",
            "TMPDIR=/native-lib",
        ]
        # fast_downward copies its installed shared library to tempfile before
        # loading it. Keep /tmp noexec; permit that native load only in this
        # bounded, isolated baseline-probe temp mount (no agent code or secrets).
        mounts += [
            "--tmpfs",
            "/native-lib:rw,exec,nosuid,nodev,size=128m,mode=1777",
        ]
        limits = {"cpus": "2", "memory": "2g", "tmpfs": "256m", "timeout": 120}
    summaries = []
    for name, tail, input_text in commands:
        identity = [image, revision, source, runtime_env, name, tail, input_text]
        if embedding_manifest is not None:
            identity += [
                embedding_manifest,
                limits,
                digest(Path(__file__).read_text(encoding="utf-8")),
            ]
        key = digest(identity)
        if alfworld_manifest is not None:
            identity += [
                alfworld_manifest,
                limits,
                digest(Path(__file__).read_text(encoding="utf-8")),
                digest(
                    (vendor / "configs/benchmark/alfworld.yaml").read_text(
                        encoding="utf-8"
                    )
                ),
            ]
            key = digest(identity)
        record = store.read("native_probes", key)
        if record is None:
            container_name = "copromem-expel-" + name + "-" + key[:8]
            label = "io.copromem.expel-probe=" + key
            command = [
                "docker",
                "run",
                "-i",
                "--name",
                container_name,
                "--label",
                label,
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--user",
                "10001:10001",
                "--cpus",
                limits["cpus"],
                "--memory",
                limits["memory"],
                "--pids-limit",
                "128",
                "--tmpfs",
                f"/tmp:rw,noexec,nosuid,size={limits['tmpfs']},mode=1777",
                *mounts,
                *[item for value in runtime_env for item in ("--env", value)],
                image,
                *tail,
            ]
            try:
                run = subprocess.run(
                    command,
                    input=input_text,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=limits["timeout"],
                    check=False,
                )
                record = {
                    "exit_code": run.returncode,
                    "stdout": run.stdout,
                    "stderr": run.stderr,
                    "timeout": False,
                }
            except subprocess.TimeoutExpired as exc:
                inspected = subprocess.run(
                    [
                        "docker",
                        "inspect",
                        "--format",
                        "{{json .Config.Labels}}",
                        container_name,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                labels = (
                    json.loads(inspected.stdout) if inspected.returncode == 0 else {}
                )
                stopped = False
                if labels.get("io.copromem.expel-probe") == key:
                    stopped = (
                        subprocess.run(
                            ["docker", "kill", container_name],
                            capture_output=True,
                            timeout=10,
                            check=False,
                        ).returncode
                        == 0
                    )
                record = {
                    "exit_code": None,
                    "timeout": True,
                    "owned_container_stopped": stopped,
                    "stdout": (exc.stdout or b"").decode("utf-8", errors="replace")
                    if isinstance(exc.stdout, bytes)
                    else (exc.stdout or ""),
                    "stderr": (exc.stderr or b"").decode("utf-8", errors="replace")
                    if isinstance(exc.stderr, bytes)
                    else (exc.stderr or ""),
                }
            record.update(
                {
                    "name": name,
                    "command": command,
                    "image_id": image,
                    "revision": revision,
                    "model_calls": 0,
                    "interpretation": "Offline unmodified official component with recorded dependency adaptation; no native rollout, embedding model, API request or published score reproduction.",
                }
            )
            if embedding_manifest is not None:
                record.update(
                    {
                        "embedding_manifest_id": args.embedding_manifest,
                        "local_embedding_inference": True,
                        "interpretation": "Unmodified native ExpeL retrieval on authored histories with a pinned local embedding checkpoint; constructors bypassed and token counter stub disclosed; no paid calls, native task rollout, learned insight or published score reproduction.",
                    }
                )
            if alfworld_manifest is not None:
                record.update(
                    {
                        "alfworld_manifest_id": args.alfworld_manifest,
                        "interpretation": "Unmodified native ExpeL environment wrapper on a pinned train-only fixture; neutral actions and native reward, no LLM/insight/solving policy or published benchmark-score reproduction.",
                    }
                )
            store.write("native_probes", key, record)
        summary = {"name": name, "record_id": key, "exit_code": record["exit_code"]}
        if (
            name
            in {
                "rule-update",
                "dependency-check",
                "native-retrieval",
                "alfworld-native-0",
                "alfworld-native-1",
            }
            or record["exit_code"] != 0
        ):
            summary["stdout"] = record.get("stdout", "")[-2500:]
            summary["stderr"] = record.get("stderr", "")[-2500:]
        summaries.append(summary)
        print(json.dumps(summary), flush=True)
    store.write("reports", digest(summaries), {"probes": summaries, "model_calls": 0})


if __name__ == "__main__":
    main()
