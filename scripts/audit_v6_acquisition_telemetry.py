#!/usr/bin/env python3
"""Produce a value-redacted integrity audit for v6 dispatcher evidence.

This utility deliberately writes only public callable names, public field
names, response status classes, and evidence digests.  It never exports task
instructions, invocation values, model text, or response bodies.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from copromem.benchmarks.appworld.execution_evidence import digest, journal_records


def _safe_issue(row: dict[str, Any], position: int) -> dict[str, Any]:
    signature = row.get("operation_signature")
    return {
        "position": position,
        "event_sha256": row.get("event_sha256"),
        "operation": row.get("operation")
        or (signature or {}).get("operation")
        or "<non_callable>",
        "schema_accepted": bool(row.get("schema_accepted")),
        "schema_error": row.get("schema_error"),
        "missing_required_public_fields": sorted(map(str, row.get("missing_required", []))),
        "unknown_public_fields": sorted(map(str, row.get("unknown_fields", []))),
        "response_success": bool(row.get("response_success")),
        "response_status": row.get("response_status"),
        "response_error_class": row.get("response_error_class"),
        "operation_signature_sha256": row.get("operation_signature_sha256"),
    }


def audit(run: Path) -> dict[str, Any]:
    acquisition = run / "acquisition"
    summaries: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for artifact in sorted(acquisition.glob("*.json")):
        row = json.loads(artifact.read_text(encoding="utf-8"))
        evidence = Path(str(row["execution_evidence_path"]))
        records = journal_records(evidence)
        schema_rejections = [
            _safe_issue(record, position)
            for position, record in enumerate(records)
            if isinstance(record.get("operation_signature"), dict)
            and not bool(record.get("schema_accepted"))
        ]
        callable_errors = [
            _safe_issue(record, position)
            for position, record in enumerate(records)
            if isinstance(record.get("operation_signature"), dict)
            and bool(record.get("schema_accepted"))
            and not bool(record.get("response_success"))
        ]
        summaries.append(
            {
                "acquisition_artifact_sha256": digest(json.loads(artifact.read_text(encoding="utf-8"))),
                "evidence_path_sha256": digest(str(evidence)),
                "evidence_records_sha256": digest(records),
                "record_count": len(records),
                "schema_rejection_count": len(schema_rejections),
                "callable_error_count": len(callable_errors),
            }
        )
        for issue in schema_rejections:
            issues.append({"kind": "schema_rejection", **issue})
        for issue in callable_errors:
            issues.append({"kind": "callable_error", **issue})
    issue_counts = Counter(
        (item["kind"], item["operation"], item["schema_error"], item["response_error_class"])
        for item in issues
    )
    result = {
        "audit_version": 1,
        "purpose": "value_redacted_v6_acquisition_telemetry_diagnosis",
        "trajectory_count": len(summaries),
        "trajectory_summaries": summaries,
        "issues": issues,
        "issue_counts": [
            {
                "kind": kind,
                "operation": operation,
                "schema_error": schema_error,
                "response_error_class": response_error_class,
                "count": count,
            }
            for (kind, operation, schema_error, response_error_class), count in sorted(issue_counts.items())
        ],
    }
    result["audit_sha256"] = digest(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.run)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"audit_sha256": report["audit_sha256"], "trajectory_count": report["trajectory_count"], "issue_count": len(report["issues"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
