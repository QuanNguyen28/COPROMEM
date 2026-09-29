# v6.2 terminal reconciliation and runtime verification

The maintained evaluation runner records a portable runtime-content identity
before preparation can become dispatch-capable.  It recomputes that identity
at startup, before each task-opening boundary, before every executor dispatch,
and immediately before terminal reconciliation.  The identity contains source
content hashes and non-secret version labels only; filesystem locations are
locators, never scientific identity.

After the final task, owned ReMe services leave their context before the
runner refreshes the ledger-derived summary and enters `reconciling`.  The
read-only terminal validator then checks the manifest, runtime record,
artifacts/evidence, Dynamic prefixes, Fixed checkpoints, ledger and process
ownership.  A failed validator writes its result and a terminal `failed`
status.  It cannot write a comparative report or `completed` status.

On success, the CoProMem Dynamic checkpoint namespace writes one atomic,
fsynced global `run-reconciled.json`.  It is chained to the last
`next_task_authorized` record and binds the manifest, runtime verification,
artifact/evidence/retrieval inventories, Fixed/Dynamic identities, checkpoint
chains, ledger, summary, terminal result, and expected count.  Reports are
written only afterwards and bind that marker.  A restart may validate an
existing marker, but may never replay a trajectory, scorer, retrieval, or
lifecycle operation to repair an incomplete terminal chain.

The state machine is therefore:

`running -> reconciling -> run_reconciled -> reports_bound -> completed`.

Any missing, inconsistent, or tampered input fails closed.  The finalizer PID
is not treated as permission for another runner or owned service to remain
alive.
