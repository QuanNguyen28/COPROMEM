"""Allowlisted ZIP extraction and parsing only: no trajectory execution/scoring."""

import hashlib
import inspect
import io
import json
import runpy
import zipfile
from dataclasses import asdict
from pathlib import Path

from appworld.common.constants import PASSWORD, SALT
from appworld.common.utils import decrypt_bytes
from appworld.environment import AppWorld

from copromem.checkpoints import canonical, digest
from copromem.official_source import (
    PUBLIC_FILES,
    parse_public_log,
    selected_member_names,
    validate_member_inventory,
)


def write_new(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def main():
    request = json.loads(Path("/request/extraction.json").read_text())
    expected_names = selected_member_names(request["run"], request["tasks"])
    assert set(expected_names) == set(request["members"])
    raw = Path("/archive/experiment-outputs-0.1.3.bundle").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == request["archive_sha256"]
    decrypted = decrypt_bytes(raw, PASSWORD, SALT)
    assert hashlib.sha256(decrypted).hexdigest() == request["zip_sha256"]
    output = Path("/selected")
    files = {}
    with zipfile.ZipFile(io.BytesIO(decrypted), "r") as archive:
        validate_member_inventory(archive.infolist(), request["members"])
        for name in expected_names:
            # The only member-body read in this program is on this exact list.
            with archive.open(name, "r") as member:
                data = member.read(1_000_001)
            assert len(data) == request["members"][name]["bytes"] <= 1_000_000
            relative = name.removeprefix(request["run"] + "/tasks/")
            target = output / "raw" / relative
            assert target.resolve().is_relative_to((output / "raw").resolve())
            write_new(target, data)
            files[relative] = {
                "archive_member": name,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
    native_parser = inspect.getsource(AppWorld._parse_environment_io_log)
    native_writer = inspect.getsource(AppWorld._save_environment_io_log)
    assert (
        hashlib.sha256(native_parser.encode()).hexdigest()
        == "ec7ca0b261e65927ba1ba77f66a1ec143b1030008018c4b86efcec9af8da3bbc"
    )
    write_new(
        output / "native_format_source.json",
        canonical({"parser": native_parser, "writer": native_writer}).encode(),
    )
    # A static syntax-policy precheck only; no AppWorld instance is constructed.
    validate = runpy.run_path("/opt/copromem-worker.py")["validate_program"]
    tasks = []
    for task in request["tasks"]:
        task_root = output / "raw" / task
        row = {
            "task_id": task,
            "files": {name: files[f"{task}/{name}"] for name in PUBLIC_FILES},
        }
        try:
            versions = {
                name: (task_root / "version" / (name + ".txt"))
                .read_bytes()
                .decode("utf-8")
                .strip()
                for name in ("code", "data")
            }
            text = (task_root / "logs/environment_io.md").read_bytes().decode("utf-8")
            interactions = parse_public_log(text)
            native = AppWorld._parse_environment_io_log(text)
            if len(native) != len(interactions):
                raise ValueError("native/lossless parser interaction counts disagree")
            changed_code, changed_output = [], []
            for interaction, old in zip(interactions, native, strict=True):
                if interaction.code != old["input"]:
                    changed_code.append(interaction.index)
                if interaction.output != old["output"]:
                    changed_output.append(interaction.index)
                # Expected native normalization only; do not accept silent loss
                # of lines caused by headers/rules/fences inside a field.
                for name, original in (
                    ("input", interaction.code),
                    ("output", interaction.output),
                ):
                    if old[name] != "\n".join(
                        line.rstrip() for line in original.split("\n")
                    ):
                        raise ValueError(
                            "native parser differs beyond documented trailing-whitespace normalization"
                        )
            api_rows = [
                json.loads(line)
                for line in (task_root / "logs/api_calls.jsonl")
                .read_bytes()
                .decode("utf-8")
                .splitlines()
                if line.strip()
            ]
            if any(not isinstance(item, dict) for item in api_rows):
                raise ValueError("API log row is not an object")
            policy_errors = []
            for interaction in interactions:
                try:
                    validate(interaction.code)
                except (SyntaxError, ValueError) as exc:
                    policy_errors.append(
                        {
                            "interaction": interaction.index,
                            "kind": type(exc).__name__,
                            "message": exc.msg
                            if isinstance(exc, SyntaxError)
                            else str(exc),
                        }
                    )
            parsed = {
                "task_id": task,
                "versions": versions,
                "interactions": [asdict(item) for item in interactions],
                "source_log_sha256": files[f"{task}/logs/environment_io.md"]["sha256"],
            }
            write_new(output / "parsed" / (task + ".json"), canonical(parsed).encode())
            row.update(
                {
                    "parse_status": "parsed",
                    "versions": versions,
                    "interactions": len(interactions),
                    "api_log_rows": len(api_rows),
                    "api_log_field_names": sorted(
                        {key for item in api_rows for key in item}
                    ),
                    "native_code_normalization_indices": changed_code,
                    "native_output_normalization_indices": changed_output,
                    "static_policy_errors": policy_errors,
                    "parsed_digest": digest(parsed),
                }
            )
        except (ValueError, TypeError, KeyError, UnicodeError) as exc:
            row.update(
                {
                    "parse_status": "rejected",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }
            )
        tasks.append(row)
    report = {
        "request_digest": digest(request),
        "members_read": expected_names,
        "files": files,
        "tasks": tasks,
        "source_format_digest": digest(
            {"parser": native_parser, "writer": native_writer}
        ),
        "paid_calls": 0,
        "task_executions": 0,
        "evaluator_payloads_read": 0,
        "db_payloads_read": 0,
        "decision": "KEEP"
        if all(row["parse_status"] == "parsed" for row in tasks)
        else "REVISE",
        "limitation": "Public source extraction/format and static code precheck only; no source-policy provenance guarantee, native outcome, replay eligibility, donor admission or memory result.",
    }
    write_new(output / "extraction_report.json", canonical(report).encode())
    print(
        json.dumps(
            {
                "decision": report["decision"],
                "files_extracted": len(files),
                "bytes_extracted": sum(row["bytes"] for row in files.values()),
                "tasks": [
                    {k: v for k, v in row.items() if k != "files"} for row in tasks
                ],
                "paid_calls": 0,
                "task_executions": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
