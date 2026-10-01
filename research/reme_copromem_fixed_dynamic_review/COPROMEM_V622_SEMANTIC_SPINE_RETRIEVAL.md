# CoProMem v6.2.2 evidence-preserving semantic spine

This is a separate method version. It does not rewrite v6.2.1 results.

## Learning contract

Every committed schema contains ordered occurrence identities, exactly covered
typed constraints, one explicit terminal occurrence or one explicit consecutive
terminal repetition group, and occurrence-level dataflow edges. A dataflow edge
is admissible only when the same producer-output/consumer-input equality was
recorded by the native dispatcher in every successful supporting trajectory.
Registry dependency metadata and equal public slot names are compatibility
metadata, never evidence that a concrete value flowed between calls.

Semantic validation is the commit gate. A base-v6 validation success cannot
commit a schema rejected by the occurrence/dataflow validator. Rejection is
byte-identical to the pre-state and binds the exact semantic validation hash.

## Retrieval contract

Retrieval starts from the explicit terminal occurrence set and traverses only
committed attested edges. Input support is occurrence-specific: an input is
supported by an incoming edge to that exact occurrence, or by the current
public task query for that operation and slot concept. A global produced-slot
set is prohibited. Registry edges cannot retain a prerequisite.

Ambiguous semantic winners abstain. Historical success count, schema ID, bank
order, and repeated-operation multiplicity cannot break a task-visible tie.
Legacy schemas without occurrence witnesses may provide terminal-only guidance
only when the terminal occurrence is unique and its inputs are independently
supported by the current public query; they cannot reconstruct prerequisites.

Every occurrence remains in provenance. Consecutive identical occurrences are
rendered as one parameterized repetition instruction with count and a hashed
occurrence inventory, preventing prompt inflation while preserving audit order.
Nonconsecutive read -> write -> read occurrences are never collapsed.

## Execution, restart, and terminal custody

The scored artifact is immutable. A separate atomic sidecar binds its exact
bytes to the task query, retrieval provenance, guidance, model-visible prompt,
and the distinct semantic and runtime-record identity domains. Restart must
recompute retrieval byte-for-byte from the frozen pre-state and validate that
sidecar before accepting or skipping an artifact. Terminal reconciliation
repeats the same checks for every CoProMem trajectory and binds the complete
retrieval inventory into `run_reconciled`.

Zero-action evidence receives both the semantic runtime identity and the hash
of `runtime-identity.json`; neither may substitute for the other. Windows keeps
native absolute evidence paths, while POSIX/WSL maps Windows drive paths to
`/mnt/<drive>`.

## Claim boundary

Passing offline tests and an engineering integration run establishes method
and custody integrity only. It does not establish efficacy, superiority, or
submission readiness. A real confirmatory pilot still requires a newly frozen
allocation, a clean detached executable checkout, zero-provider preflight, and
successful terminal reconciliation.
