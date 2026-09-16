"""Unmodified Ruff F821 adapter over public source and optional presence stubs."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import keyword
import re
import runpy
import subprocess
from pathlib import Path

from copromem.checkpoints import IntegrityError, digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PUBLIC = runpy.run_path(str(HERE / "public_presence.py"))
VERSION = "isolated-ruff-f821-public-presence-analysis-only-v1"
FILENAME = "copromem_registered_action.py"
OPTIONS = [
    "check",
    "--isolated",
    "--no-cache",
    "--target-version",
    "py312",
    "--select",
    "F821",
    "--output-format",
    "json",
    "--stdin-filename",
    FILENAME,
    "-",
]


def invocation(executable: str, args: list[str], stdin: str | None = None) -> dict:
    command = [executable, *args]
    result = subprocess.run(
        command,
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
        timeout=30,
        check=False,
    )
    return {
        "argv": command,
        "cwd": str(ROOT),
        "stdin": stdin,
        "stdin_digest": digest(stdin),
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.returncode,
    }


def tool_profile() -> dict:
    from ruff import find_ruff_bin

    executable = Path(find_ruff_bin()).resolve()
    return {
        "executable": str(executable),
        "binary_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "package_version": importlib.metadata.version("ruff"),
        "version_call": invocation(str(executable), ["--version"]),
        "rule_call": invocation(str(executable), ["rule", "F821"]),
    }


def verify_tool(profile: dict) -> None:
    path = Path(profile["executable"])
    if (
        not path.is_file()
        or hashlib.sha256(path.read_bytes()).hexdigest() != profile["binary_sha256"]
        or importlib.metadata.version("ruff") != profile["package_version"]
        or profile["version_call"]["exit_code"] != 0
        or profile["rule_call"]["exit_code"] != 0
    ):
        raise IntegrityError("installed checker/version differs from recorded tool")


def validate_public(public: dict) -> dict[str, bool]:
    if (
        not isinstance(public, dict)
        or set(public) != {"program", "envelope"}
        or not isinstance(public["program"], str)
    ):
        raise ValueError("checker accepts only source text and public envelope")
    envelope = public["envelope"]
    if (
        not isinstance(envelope, dict)
        or set(envelope) != {"version", "bindings"}
        or envelope["version"] != PUBLIC["VERSION"]
        or not isinstance(envelope["bindings"], list)
    ):
        raise ValueError("invalid public presence envelope")
    observations = {}
    for item in envelope["bindings"]:
        if (
            not isinstance(item, dict)
            or set(item) != {"name", "present"}
            or not isinstance(item["name"], str)
            or not item["name"].isidentifier()
            or keyword.iskeyword(item["name"])
            or type(item["present"]) is not bool
            or item["name"] in observations
        ):
            raise ValueError("invalid or duplicate name-presence observation")
        observations[item["name"]] = item["present"]
    if list(observations) != sorted(observations):
        raise ValueError("presence registry is out of order")
    return observations


def analysis_input(public: dict, *, context: bool) -> dict:
    observations = validate_public(public)
    # Compile nothing and execute nothing: these declarations are lint input only.
    provided = sorted(
        {"apis"}
        | ({n for n, present in observations.items() if present} if context else set())
    )
    stubs = "".join(name + " = None\n" for name in provided)
    names = PUBLIC["selected_names"]([public["program"]])
    unknown = sorted(set(names) - set(observations))
    return {
        "source": stubs + public["program"],
        "line_offset": len(provided),
        "provided_names": provided,
        "queried_names": sorted(observations),
        "present_names": sorted(n for n, present in observations.items() if present),
        "absent_names": sorted(n for n, present in observations.items() if not present),
        "unknown_names": unknown,
        "covered": not unknown,
        "analysis_only_stubs": True,
        "context": context,
        "program_digest": digest(public["program"]),
    }


def local_label(output: str | None) -> dict:
    if not isinstance(output, str) or not output.strip():
        return {"label": None, "kind": "missing_or_empty_public_output", "name": None}
    if not output.startswith("Execution failed."):
        return {"label": False, "kind": "no_uncaught_execution_error", "name": None}
    final = output.strip().splitlines()[-1].strip()
    match = re.fullmatch(
        r"NameError: name ['\"]([^'\"]+)['\"] is not defined(?:\. Did you mean: .*)?",
        final,
    )
    if match and match[1].isidentifier():
        return {"label": True, "kind": "uncaught_missing_name", "name": match[1]}
    if final.startswith("NameError:"):
        return {"label": None, "kind": "ambiguous_name_error", "name": None}
    return {"label": None, "kind": "other_or_ambiguous_execution_failure", "name": None}


def parse_findings(process: dict, submitted: dict) -> dict:
    if process["exit_code"] not in (0, 1):
        return {
            "valid": False,
            "error": "checker_process_error",
            "findings": [],
            "warning_names": [],
        }
    if process["stderr"].strip():
        return {
            "valid": False,
            "error": "unexpected_checker_stderr",
            "findings": [],
            "warning_names": [],
        }
    try:
        findings = json.loads(process["stdout"])
    except json.JSONDecodeError:
        return {
            "valid": False,
            "error": "malformed_checker_json",
            "findings": [],
            "warning_names": [],
        }
    if not isinstance(findings, list) or (process["exit_code"] == 0) != (
        len(findings) == 0
    ):
        return {
            "valid": False,
            "error": "checker_exit_findings_disagree",
            "findings": [],
            "warning_names": [],
        }
    converted, names = [], set()
    lines = submitted["source"].splitlines()
    for finding in findings:
        try:
            code, start, end = (
                finding["code"],
                finding["location"],
                finding["end_location"],
            )
            row, column, end_row, end_column = (
                start["row"],
                start["column"],
                end["row"],
                end["column"],
            )
            if (
                code != "F821"
                or any(type(v) is not int for v in (row, column, end_row, end_column))
                or row != end_row
                or not submitted["line_offset"] < row <= len(lines)
                or not 1 <= column < end_column <= len(lines[row - 1]) + 1
                or Path(finding["filename"]).resolve() != (ROOT / FILENAME).resolve()
            ):
                raise ValueError("invalid diagnostic location/rule")
            name = lines[row - 1][column - 1 : end_column - 1]
            if (
                not name.isidentifier()
                or finding["message"] != f"Undefined name `{name}`"
            ):
                raise ValueError("diagnostic does not match source identifier")
            converted.append(
                {
                    "name": name,
                    "original_row": row - submitted["line_offset"],
                    "column": column,
                    "end_column": end_column,
                    "raw_finding": finding,
                }
            )
            names.add(name)
        except (KeyError, TypeError, ValueError, IndexError):
            return {
                "valid": False,
                "error": "invalid_f821_schema_or_source_mapping",
                "findings": [],
                "warning_names": [],
            }
    return {
        "valid": True,
        "error": None,
        "findings": converted,
        "warning_names": sorted(names),
    }
