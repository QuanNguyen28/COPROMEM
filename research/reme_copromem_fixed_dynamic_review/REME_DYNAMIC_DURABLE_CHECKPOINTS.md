# Durable official ReMe Dynamic checkpoints

This boundary protects the official upstream `dynamic_post_trial_update` call
used by the v6.1 exploratory runner. It does not replace, reinterpret, or
locally imitate the upstream lifecycle.

## Durable order

After an AppWorld score and its evidence-bound scored artifact are durable, the
runner dumps the current Dynamic bank and writes an atomic, fsynced intent. The
intent binds the frozen update order, artifact and execution-evidence hashes,
upstream retrieval identity, pre-update semantic hash, predecessor marker, and
ledger byte boundary. It then invokes the upstream lifecycle exactly once.

The updated bank is dumped to an E-backed snapshot, fsynced, loaded into a
separate `reme-dynamic-verifier` service with `clear_existing=true`, and dumped
again. The manager requires identical memory IDs and non-vector fields, vector
agreement within the maintained float32 tolerance, and equal semantic hashes.
Only then is an atomic, fsynced completion marker written. The marker binds the
intent, source/verifier snapshots, pre/post state, score/evidence/retrieval
inputs, order, and newly settled Dynamic lifecycle or embedding request IDs.

## Restart state machine

`none -> intent -> snapshot + verifier -> completion marker` is the only valid
transition. Reconciliation accepts an exact ordered prefix of fully validated
markers and snapshots. It restores that latest snapshot only after validation;
two independent verifier dumps must reproduce it. An intent without a marker,
a snapshot without a marker, a marker without a snapshot, any hash/order/input
mismatch, or an orphaned checkpoint is fail-closed. The boundary never retries
or replays a provider-backed update.

## Strict callback

`execute_trajectory` retains historical best-effort callbacks by default.
The ReMe Dynamic runner passes `post_score_update_strict=True`: after the score
artifact exists, a checkpoint callback failure is durably logged and propagated
to stop the runner before its next trajectory. The score is not removed or
replayed. Fixed ReMe never enters this checkpoint namespace and remains
read-only.

## Verifier invariant

`reme-dynamic-verifier` may only load and dump an existing snapshot. Any model,
lifecycle, or embedding provider operation by that service violates the
boundary and is fatal.
