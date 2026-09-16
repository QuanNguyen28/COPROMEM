# Cycle 16A: bounded 100-action source-replay runtime gate

Registered 2026-09-16 before building or running the enlarged source runtime.
Zero model calls and zero paid API budget. Goal remains active. Preserve the old
50-action image, original worker file, all old evidence and reserved partitions.

The extracted official corpus contains one 85-action record. Truncating it would
change the program sequence; silently dropping it would narrow the fixed source
sample. Create an explicit **source-replay-only 100-action image** by wrapping
the unchanged trusted worker module and changing only its action-cap constant.
Its native interaction budget consequently becomes 104, matching the existing
four-interaction accounting allowance. Keep language/namespace policy, per-action
API limit 100, 15-second timeout, dependencies, user/network/mount/capability
isolation, request size and evaluator unchanged. Do not alter the 50-action
source-collection policies or claim equal source acquisition costs.

Before any archived official sequence is executed, freeze and test two cases:

1. On already allocated build task `27e1026_1`, seed 100, a 100-action authored
   counter-only fixture: initialize `counter=0`, then 99 increments/prints. Verify
   final counter 99, complete 100-action recording, advertised capacity 100,
   supported namespace and exact independent live-stream/fresh-prefix equivalence,
   including native scorer equality. This is an engineering fixture, not a solved
   benchmark task or learned intervention.
2. Re-execute the exact saved successful cycle-11 `aa8502b_1` replicate-1 prefix
   from its original public bundle. Verify two independent new executions, native
   scoring, and equality to the old public observations, DB state, complete
   supported namespace/state digest and completion status. Ignore only the
   deliberately versioned top-level advertised action-cap field; do not normalize
   task effects or rewrite old artifacts. Expected action errors come from the
   original archived record, not a guessed clean trace.

**KEEP** the bounded runtime only if both cases pass; otherwise **REVISE** the
implementation with all failed attempts retained and no official-source replay.
Tests of 100/101 action request acceptance/rejection must accompany this change.
The 100-action fixture is checked at the boundary, not merely at 51 actions.

Record full image/build/source hashes, requests, per-boundary frames, raw process
output, expected errors, scorer records, timings and independent audits. Partial
native runs must not restart silently or overwrite data. This is not a proof
for arbitrary Python, a cure for unsupported `Match` state, or source-policy
quality. Runtime expansion cannot promote old excluded episodes retroactively.

Only after this gate passes may a separate frozen cycle-16B protocol replay all
eight extracted official traces unchanged, without model calls or archive
evaluator/DB access. Its native outcomes and eligibility are currently unknown.
