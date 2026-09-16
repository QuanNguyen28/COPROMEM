"""Unique intact JSON-object extraction; no model call or generated-code edit."""

from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = runpy.run_path(str(HERE / "teacher_repair_source.py"))
VERSION = "cycle24b-unique-intact-proposal-object-compatibility-v1"
SOURCE_PROTOCOL = "bc4ee11f08d444cc03f4daf12437060ffa035fd5793b88d09152d8fde62b66a5"
SOURCE_REPORT = "95964b682326d291f23b30e651f9e4bc46c96e2f3991a2a0c276e1c2614d2971"


def extract(text, allowed):
    decoder = json.JSONDecoder()
    found = []
    for start, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, length = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and set(value) == {
            "action_index",
            "code",
            "diagnosis",
        }:
            found.append((start, start + length))
    if len(found) != 1:
        raise ValueError("proposal object is missing or ambiguous")
    start, end = found[0]
    raw = text[start:end]
    parsed = BASE["parse_proposal"](raw, allowed)
    return parsed, {
        "raw_response_text_digest": digest(text),
        "object_substring_digest": digest(raw),
        "object_start_character": start,
        "object_end_character": end,
        "object_start_utf8_byte": len(text[:start].encode()),
        "object_end_utf8_byte": len(text[:end].encode()),
        "prefix_digest": digest(text[:start]),
        "suffix_digest": digest(text[end:]),
        "decoded_code_digest": digest(parsed["code"]),
        "code_modified": False,
    }


def prepare(store):
    source = RunStore(ROOT / "artifacts/research/cycle24_teacher_repair_source_v2")
    protocol = source.read("protocol", "preregistration")
    report = source.read("proposal_reports", SOURCE_REPORT)
    if digest(protocol) != SOURCE_PROTOCOL or digest(report) != SOURCE_REPORT:
        raise IntegrityError("strict collection provenance changed")
    snapshot = source.read("source_snapshots", protocol["source_snapshot"])
    if digest(snapshot) != protocol["source_snapshot"] or any(
        (ROOT / n).read_text(encoding="utf-8") != t for n, t in snapshot.items()
    ):
        raise IntegrityError("strict implementation changed before compatibility")
    slots, rows = [], []
    for slot, strict in zip(protocol["slots"], report["rows"], strict=True):
        if strict["key"] != slot["key"] or strict["status"] != "invalid_proposal":
            raise IntegrityError("unexpected strict source slot/status")
        call = source.read("calls", strict["request_id"])
        if (
            digest(call["request"]) != strict["request_id"]
            or digest(call["response"]) != call["response_sha256"]
        ):
            raise IntegrityError("teacher response identity changed")
        payload = source.read("teacher_inputs", slot["input_digest"])
        if digest(payload) != slot["input_digest"] or call["request"]["user"] != BASE[
            "canonical"
        ](payload):
            raise IntegrityError("teacher response attached to wrong input")
        try:
            parsed, extraction = extract(
                call["response"]["text"], slot["eligible_indices"]
            )
        except (ValueError, SyntaxError, TypeError) as exc:
            row = {
                "key": slot["key"],
                "status": "invalid_compatibility_proposal",
                "error_type": type(exc).__name__,
            }
        else:
            row = {
                "key": slot["key"],
                "request_id": strict["request_id"],
                "extraction": extraction,
                **parsed,
            }
            if parsed["status"] == "valid_proposal":
                origin = source.read(
                    "origins", f"{slot['key']}-{parsed['action_index']:02d}"
                )
                candidate = BASE["effect_candidate"](
                    slot, origin, strict["request_id"], parsed
                )
                store.write("effect_candidates", digest(candidate), candidate)
                row["candidate_id"] = digest(candidate)
        store.write("proposal_results", slot["key"], row)
        rows.append(row)
        slots.append(slot)
    paths = (
        Path(__file__).resolve(),
        ROOT / "tests/test_teacher_repair_compat.py",
        ROOT / "research/064_CYCLE24_STRICT_RESULT_AND_FORMAT_COMPATIBILITY.md",
    )
    texts = {
        p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8") for p in paths
    }
    compatible = {
        "version": VERSION,
        "source_protocol": SOURCE_PROTOCOL,
        "source_report": SOURCE_REPORT,
        "source_snapshot": digest(texts),
        "parent_source_snapshot": protocol["source_snapshot"],
        "slots": slots,
        "public_bundle": protocol["public_bundle"],
        "native_data": protocol["native_data"],
        "image_id": protocol["image_id"],
        "new_model_calls": 0,
        "new_api_usd": 0,
        "inherited_teacher_usd": report["settled_usd"],
    }
    store.bind_provenance({"protocol_digest": digest(compatible)})
    store.write("protocol", "preregistration", compatible)
    store.write("source_snapshots", digest(texts), texts)
    diagnostic = {
        "protocol_digest": digest(compatible),
        "rows": rows,
        "valid_compatible_proposals": sum(
            r["status"] == "valid_proposal" for r in rows
        ),
        "planned_tasks": 4,
        "model_calls": 0,
        "new_api_usd": 0,
        "inherited_teacher_usd": report["settled_usd"],
    }
    store.write("compatibility_reports", digest(diagnostic), diagnostic)
    return compatible, diagnostic


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--effects", action="store_true")
    args = parser.parse_args()
    store = RunStore(ROOT / "artifacts/research/cycle24b_teacher_format_compat")
    protocol, report = prepare(store)
    if args.effects:
        report = BASE["effects"](store, protocol)
    print(
        json.dumps(
            {
                "report_digest": digest(report),
                **{k: v for k, v in report.items() if k != "rows"},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
