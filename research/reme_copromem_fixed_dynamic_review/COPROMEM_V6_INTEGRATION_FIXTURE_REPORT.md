# v6 contrastive-graph integration fixture 001

`v6_integration_fixture_001_contrastive_graph` is a deterministic, zero-provider engineering fixture. It is not an AppWorld benchmark run and is excluded from efficacy statistics.

It runs the production `ContrastiveV6Dispatcher`, `SharedTrajectoryExecutor` interface, public-execution-evidence v1 journal, telemetry partition, v6 graph builder/planner/validator/committer, durable transition recovery, retrieval implementation, and a zero-value append-only ledger. A local fixture executor and scorer are the only mocked boundaries: no AppWorld payload or official scorer is opened because this protocol forbids benchmark payload access.

The fixture uses three same-pre-state A trajectories (two successful, one failed) with different optional discovery paths, a shared typed read/write core, negative exploration evidence, and repeated dispatcher calls. It promotes only through the production contrastive lifecycle. B retrieval then uses the committed A state twice; an incompatible negative B query receives empty guidance.

Run it without a provider or benchmark payload:

```bash
PYTHONPATH=src /mnt/e/Project/AAMAS/reme-env/bin/python scripts/run_v6_integration_fixture.py \
  --root /mnt/e/Project/AAMAS/COPROMEM-review/artifacts/zero-cost-validation/v6_integration_fixture_001
```

The artifact directory contains `final-fixture-report.json`, `state-machine-transition-record.json`, `promoted-schema-audit.json`, `a-to-b-retrieval-audit.json`, `restarts/restart-replay-matrix.json`, and `evidence-checksums.json`. Every output is value-redacted; concrete invocation values are retained only as hashes in telemetry and never enter the promoted schema.

The restart matrix covers telemetry-before-score, score-before-artifact, batch-ready, plan, validation, commit, and one persisted B retrieval. Each restart reuses durable records and asserts no repeated local action or scorer boundary. Fixed-mode retrieval is exercised against an unchanged committed state. Negative cases cover insufficient support, no common core, missing terminal effect, malformed telemetry, audit-only rows, callable errors, concrete-value leakage, and tampered retrieval provenance.

The expected passing classification is: `ENGINEERING-VALIDATED: v6 contrastive schema induction, transactional commit, restart recovery, and A→B retrieval work end-to-end under deterministic evidence.`
