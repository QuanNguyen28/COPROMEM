"""Build a frozen v6.2.7 multi-schema admission bundle without provider calls."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from copromem.experiments.reme_copromem import task_conditioned_retrieval_v627 as retrieval
from copromem.experiments.reme_copromem.schema_multi_admission import bundle, schema_identity, verify


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build(*, bank_path: Path, receipt_paths: list[Path]) -> dict[str, Any]:
    state = load_json(bank_path)
    schemas = retrieval.base._schema_rows(state)
    entries = []
    for path in receipt_paths:
        receipt = load_json(path)
        ids = receipt.get("schema_ids")
        if not isinstance(ids, list) or len(ids) != 1 or not isinstance(ids[0], str):
            raise ValueError(f"receipt must bind exactly one schema: {path}")
        schema_id = ids[0]
        schema = schemas.get(schema_id)
        if schema is None:
            raise ValueError(f"receipt schema absent from frozen bank: {schema_id}")
        entries.append({"schema_id": schema_id, "schema_identity_sha256": schema_identity(schema),
                        "external_admission_receipt": receipt})
    result = bundle(policy_sha256=retrieval.frozen_policy()["policy_sha256"], entries=entries)
    verify(result, policy_sha256=retrieval.frozen_policy()["policy_sha256"], schemas=schemas)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bank", required=True, type=Path)
    parser.add_argument("--receipt", required=True, action="append", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("refusing to overwrite immutable admission bundle")
    result = build(bank_path=args.bank.resolve(), receipt_paths=[item.resolve() for item in args.receipt])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")

if __name__ == "__main__":
    main()

