"""Build a separate import-only ExpeL environment; archive every build attempt."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from copromem.checkpoints import RunStore, digest


def main():
    # The Windows console may be CP1252 while Docker emits Unicode progress bars.
    # Keep raw output in the archive and escape only console-unrepresentable glyphs.
    sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dockerfile", choices=["Dockerfile", "Dockerfile.full"], default="Dockerfile"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    context = root / "research/containers/expel"
    sources = {
        path.name: path.read_text(encoding="utf-8")
        for path in context.iterdir()
        if path.is_file()
    }
    source_id = digest({"sources": sources, "dockerfile": args.dockerfile})
    tag = "copromem-expel-probe:build-" + source_id[:12]
    store = RunStore(root / "artifacts/research/expel_native_probe_20260916")
    store.write("build_sources", source_id, sources)
    previous = store.read("builds", source_id)
    if previous is not None:
        print(
            json.dumps(
                {"cached_build_evidence": previous["exit_code"], "source_id": source_id}
            )
        )
        return
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
        "command": command,
        "source_id": source_id,
        "exit_code": status,
        "output": "".join(lines),
        "interpretation": (
            "Upstream requirements plus explicit CPU/compatibility constraints; no native rollout, embedding download or published score reproduction."
            if args.dockerfile == "Dockerfile.full"
            else "Import/CLI environment only; no full dependencies, native rollout or published score reproduction."
        ),
    }
    if status == 0:
        record["image_id"] = subprocess.check_output(
            [
                "docker",
                "image",
                "inspect",
                tag,
                "--format",
                "{{.Id}}",
            ],
            text=True,
        ).strip()
    store.write("builds", source_id, record)
    print(
        json.dumps(
            {key: value for key, value in record.items() if key != "output"}, indent=2
        )
    )
    raise SystemExit(status)


if __name__ == "__main__":
    main()
