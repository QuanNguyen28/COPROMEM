# Evaluation 001 payload-exposure audit

`v6_2_task_conditioned_evaluation_001` is immutable.  This zero-provider audit
uses only its durable worker, journal, scorer, ledger, and artifact paths.

* **Opened/executed/scored-by-worker/evidence-bearing:** `024c982_1`.
  It has a worker/action journal, response-attested journal, official scorer
  records, and ten settled executor calls.  It is permanently excluded from
  successor and confirmatory allocations.
* **Selected but unopened:** the remaining 29 manifest IDs.  They have no
  worker start, action/scorer journal, response-attested journal, artifact, or
  task-specific executor settlement in the failed-run directory.

Manifest selection alone is not treated as payload exposure.  No other task
was opened before the evidence-contract failure.  The corresponding
machine-readable audit is `v62-evaluation-001-exposure-audit.json`; it contains
only task IDs and custody classes, not payloads or task contents.
