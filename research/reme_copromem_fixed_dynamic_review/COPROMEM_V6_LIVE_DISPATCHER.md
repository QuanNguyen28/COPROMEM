# CoProMem v6 live dispatcher

`copromem.experiments.reme_copromem.contrastive_v6_dispatcher.ContrastiveV6Dispatcher`
owns v6 orchestration only. It injects the existing shared executor (which will
call `execute_trajectory`), ledger, AppWorld worker, official scorer and public
execution-evidence journal; it duplicates none of those boundaries.

For every task it fsyncs immutable content-addressed transition records under
`state-machine/<task>/`: initialized, task_pre_state_frozen,
retrievals_materialized, trajectories_complete, batch_ready, plan_persisted,
validation_persisted, commit_persisted, next_task_authorized, and finalized.
Retrievals and trajectory artifacts are separate, making both same-task trials
start from one identical frozen state.

The dispatcher does not open benchmark tasks. A future launch adapter injects
the shared executor and durable score/evidence paths. Restart validates hashes
and resumes only at the first missing transition; unsettled reservations and
state/hash mismatches fail closed. It imports only the pure v6 contrastive
lifecycle, never the v5.3 exact-path lifecycle.
