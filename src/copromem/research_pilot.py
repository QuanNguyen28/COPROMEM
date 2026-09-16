"""Configuration-driven development pilot; never reads GSM8K final test data."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from .checkpoints import RunStore, digest
from .paired_gsm8k import PairedConfig, run_paired_experiment
from .providers import BudgetedOpenRouterClient, BudgetLedger, model_endpoints
from .real_gsm8k_experiment import Example, fetch_split, load_env


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--env", type=Path, default=Path(".env"))
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    store = RunStore(Path(config["output_directory"]))
    store.write("protocol", "preregistration", config)
    source_root = Path(__file__).resolve().parent
    provenance = {
        "branch": subprocess.check_output(
            ["git", "branch", "--show-current"], text=True
        ).strip(),
        "commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "source_hashes": {
            path.name: digest(path.read_text(encoding="utf-8"))
            for path in sorted(source_root.glob("*.py"))
        },
    }
    store.bind_provenance(provenance)
    source_snapshot = {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(source_root.glob("*.py"))
    }
    store.write("source_snapshots", digest(source_snapshot), source_snapshot)
    selected = store.read("dataset", "development_selection")
    if selected is None:
        training = fetch_split("train")
        ordered = sorted(
            training, key=lambda x: digest([config["selection_seed"], x.example_id])
        )
        build_size, eval_size = config["build_size"], config["evaluation_size"]
        selected = {
            "source": "official GSM8K train only",
            "selection": "hash ranking of IDs; independent of answers, lengths or outcomes",
            "build": [{**asdict(x), "gold": str(x.gold)} for x in ordered[:build_size]],
            "development": [
                {**asdict(x), "gold": str(x.gold)}
                for x in ordered[build_size : build_size + eval_size]
            ],
        }
        store.write("dataset", "development_selection", selected)
    convert = lambda items: [
        Example(x["example_id"], x["question"], Decimal(x["gold"])) for x in items
    ]
    metadata = store.read("provider", "metadata")
    if metadata is None:
        metadata = model_endpoints(config["model"])
        store.write("provider", "metadata", metadata)
    key = load_env(args.env).get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not configured")
    ledger = BudgetLedger(store, config["max_usd"], config["max_http_attempts"])
    client = BudgetedOpenRouterClient(key, config["model"], config["provider"], ledger)
    protocol = PairedConfig(
        seed=config["seed"],
        replicates=config["replicates"],
        namespace=config["cycle_id"],
    )
    report = run_paired_experiment(
        client,
        convert(selected["build"]),
        convert(selected["development"]),
        {"id": config["model"], "provider": config["provider"]},
        config=protocol,
        store_path=store.root,
    )
    report["budget"] = {
        "cap_usd": ledger.max_usd,
        "charged_or_reserved_usd": ledger.charged_or_reserved,
        "total_http_reservations": len(ledger.reservations),
    }
    report["provenance"] = provenance
    store.write("reports", digest(report), report)
    print(
        json.dumps(
            {
                "report_id": digest(report),
                "budget": report["budget"],
                "totals": report["experiment_totals"],
                "accuracy": {
                    name: value["metrics"]["task_success"]["pass_at_1"]
                    for name, value in report["evaluation"].items()
                },
                "paired": {
                    name: {k: v for k, v in value.items() if k != "details"}
                    for name, value in report["paired"].items()
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
