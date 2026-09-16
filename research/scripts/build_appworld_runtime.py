"""Build a source-snapshotted AppWorld runtime; preserve all build evidence."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from copromem.checkpoints import RunStore, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dockerfile",
        choices=["Dockerfile", "Dockerfile.longsource"],
        default="Dockerfile",
    )
    parser.add_argument(
        "--store", type=Path, default=Path("artifacts/research/cycle10_runtime_gate")
    )
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="backslashreplace")
    root = Path(__file__).resolve().parents[2]
    context = root / "research/containers/appworld"
    store = RunStore(root / args.store)
    sources = {
        path.name: path.read_text(encoding="utf-8")
        for path in context.iterdir()
        if path.is_file()
    }
    key = (
        digest(sources)
        if args.dockerfile == "Dockerfile"
        else digest({"sources": sources, "dockerfile": args.dockerfile})
    )
    store.write("build_sources", key, sources)
    previous = store.read("builds", key)
    if previous is not None:
        print(
            json.dumps({k: v for k, v in previous.items() if k != "output"}, indent=2)
        )
        raise SystemExit(previous["exit_code"])
    tag = "copromem-appworld:runtime-" + key[:12]
    command = [
        "docker",
        "build",
        "--progress=plain",
        "-t",
        tag,
        "-f",
        str(context / args.dockerfile),
        str(context),
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    lines = []
    for line in process.stdout:
        lines.append(line)
        print(line, end="", flush=True)
    status = process.wait()
    record = {
        "source_id": key,
        "command": command,
        "exit_code": status,
        "output": "".join(lines),
        "model_calls": 0,
        "interpretation": "Runtime build only; no task/learned-method efficacy or general checkpoint equivalence claim.",
    }
    if status == 0:
        record["image_id"] = subprocess.check_output(
            ["docker", "image", "inspect", tag, "--format", "{{.Id}}"],
            text=True,
        ).strip()
    store.write("builds", key, record)
    print(json.dumps({k: v for k, v in record.items() if k != "output"}, indent=2))
    raise SystemExit(status)


if __name__ == "__main__":
    main()
