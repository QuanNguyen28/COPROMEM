# v6.1 ledger-derived live summary

`live_summary.py` is a read-only accounting boundary. It parses the
append-only ledger and validated evaluation artifacts, returns an immutable
reconciliation result, and atomically writes `live-summary.json`. It never
modifies the ledger.

## Ledger events and ownership

Each reservation ID occurs once and is followed by at most one settlement. A
duplicate, an orphan settlement, malformed/non-finite/negative USD amount,
role change, model/provider mismatch, or unregistered role fails closed.
Identical duplicate rows are not accepted because the ledger contract itself
does not permit duplicate call IDs.

Executor roles have the frozen form
`executor:<arm>:<task>:trial=<trial>:seed=<seed>` and are attributed to that
arm. `reme_lifecycle:reme-fixed` and `reme_embedding:reme-fixed` belong to
official ReMe Fixed; their `reme-dynamic` counterparts belong to official ReMe
Dynamic. Provider activity by `reme-dynamic-verifier` is fatal. CoProMem
decomposition is forbidden for frozen v6.1 evaluation because its bank is
already recovered. The single `historical-construction-carry` record is kept
separately and is never assigned to an arm.

## Summary equations

For each arm, the summary reports completed/scored trajectory statistics plus
executor, lifecycle, and embedding call counts and costs. The sum of arm costs
must equal settled evaluation cost. Adding the manifest-pinned historical
settlement yields total ledger exposure. Unresolved reservation IDs are exposed
immediately and prohibit final completion.

Only validated artifacts beneath the current run's artifact root count. Each
must have a registered identity, numeric official score, nonempty canonical
history and matching hash, action-count agreement, and—when telemetry is
required—a valid absolute evidence journal/hash/registry binding. Predecessor
run artifacts are never passed to this boundary and cannot enter a successor
summary.

## Restart and final completion

Repeated reads of unchanged files return the same result; `updated_ns` is the
only write-time field. The runner refreshes the summary after each score,
Dynamic checkpoint, CoProMem task update, startup reconciliation, and terminal
transition. Final completion requires exactly 60 unique allocated trajectories,
12 per arm, every task/trial/seed identity exactly once, and no unresolved
reservation.
