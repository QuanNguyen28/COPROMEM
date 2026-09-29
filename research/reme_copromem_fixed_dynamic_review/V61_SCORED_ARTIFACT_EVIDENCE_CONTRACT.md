# Scored-artifact execution-evidence contract v1

`scored-execution-evidence-v1` is the sole contract between the execution
producer and every evaluation consumer.  A scored artifact must bind these
exact fields:

- `execution_evidence_path`: an existing absolute journal path;
- `execution_evidence_sha256`: SHA-256 of the journal bytes;
- `execution_evidence_rows`: the positive JSONL row count;
- `execution_evidence_registry_sha256`: frozen callable-registry identity;
- `execution_evidence_run_relative`: canonical locator below the run root;
- `execution_evidence_contract_version`.

The producer writes these after the AppWorld guard has restored and the journal
has been flushed.  Reconciliation, dynamic updates, live summary, restart,
and report generation validate the same fields.  Missing, renamed, duplicate,
conflicting, version-mismatched, escaped, or tampered bindings fail closed.

Evaluation 004's valid No Memory artifact used the established canonical names
`execution_evidence_run_relative` and
`execution_evidence_registry_sha256`.  An external handoff check incorrectly
looked for aliases and caused the interruption; this contract prevents a
repeat without weakening validation.
