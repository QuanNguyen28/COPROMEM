# v6 dispatcher offline verification

Tests use injected fake executor and lifecycle boundaries only. They exercise
same-task state isolation, immutable transition writes, complete-batch planning,
idempotent restart, and fail-closed ledger/pre-state reconciliation. No test
selects a task, loads a payload, contacts a provider, starts AppWorld, or calls
an official scorer. A source-level assertion rejects a v5.3 lifecycle import.
