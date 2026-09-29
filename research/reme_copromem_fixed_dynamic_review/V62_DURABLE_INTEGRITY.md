# v6.2 durable integrity and restart contract

This is an offline contract for a later separately authorized evaluation. It
does not create a manifest, task allocation, service, or provider request.

## CoProMem Dynamic transition prefix

For each task, `CoProMemDynamicCheckpointManager` writes immutable,
content-addressed transition records in this order:

1. `task_pre_state_frozen`
2. `retrievals_materialized`
3. `trajectories_complete`
4. `batch_ready`
5. `semantic_plan_persisted`
6. `validation_persisted`
7. `commit_persisted`
8. `post_state_snapshot_persisted`
9. `next_task_authorized`

Every record binds manifest, source, registry, task order, and predecessor
file hash. Pre/post snapshots separately record file and semantic hashes.
Restart validates the longest contiguous prefix, restores only the last valid
post-state, preserves valid artifacts/retrievals, and exposes the exact next
transition. A gap, reordering, imported record, snapshot/marker mismatch,
Fixed-state drift, or unresolved reservation is fail-closed. A rejected
update must retain its exact pre-state and no winner schema.

## ReMe boundaries

`ReMeDynamicCheckpointManager` owns ordered online post-score updates. An
intent without its reload-tested marker/snapshot is ambiguous and cannot be
replayed. The verifier only loads/dumps existing snapshots and must not make a
provider request.

`ReMeFixedIntegrityManager` dumps the official Fixed service locally at
initialization, each completed task boundary, and terminal completion. It
records file and semantic hashes separately; harmless JSON serialization order
does not count as mutation, semantic drift does. A forbidden Fixed mutation
role or an incomplete checkpoint chain is fail-closed.

## Runtime identity and terminal gate

Runtime identities hash file/tree content without serializing absolute machine
paths. Required content includes the maintained runner and bridge, pinned
upstream ReMe/AppWorld/agent/scorer identities, registry, lock/environment
identity, Python version, and protocol-decision hash. Content drift fails
before payload access.

`validate_terminal_run` is read-only and returns every detected discrepancy:
manifest/runtime identity, evidence/scorer bindings, artifact identity,
ledger/live-summary reconciliation, CoProMem and ReMe checkpoint prefixes,
Fixed semantic identity, and owned-process status. It must not generate an
efficacy report if any failure is present.

## Trial terminology and method boundary

Numeric values retained for stable artifact identities are
`stochastic_trial_id` values. `provider_seed` is explicitly null; no bitwise
replication claim is permitted. Official upstream ReMe Dynamic remains ordered
online adaptation. CoProMem Dynamic remains same-pre-task, task-batch
adaptation. v5 winner memory and proposed v6.3 structured guidance remain
separate methods.

## Zero-provider verification

The maintained fixtures cover crash points before/after each transition,
tampered snapshots/records, state/order drift, no-replay reconciliation, Fixed
immutability, runtime content drift, stochastic terminology, and multi-error
terminal failure reporting. All use local fake files/services only.
