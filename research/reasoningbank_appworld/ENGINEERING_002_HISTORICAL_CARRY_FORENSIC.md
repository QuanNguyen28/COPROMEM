# Engineering 002 historical-carry summary failure

`reasoningbank_appworld_engineering_002` is preserved as an
infrastructure-failed attempt.  It stopped after one durable No Memory
trajectory because the generic live-summary reconciler accepted only the
legacy literal historical carry ID.  The successor correctly used the distinct
`historical-infrastructure-carry` ID for prior-run exposure, but did not pass
that declared identity into the reconciler.

The failure was `LedgerReconciliationError: unexpected historical
carry-forward call ID`.  It occurred during summary refresh after scoring, not
during task selection, execution-evidence writing, scoring, or a Dynamic
update.  The manifest, ledger, and scored artifact remain immutable.  The
repair makes the manifest-declared historical carry identity an explicit
reconciliation argument; it does not change provider routing, the method, task
allocation, scores, or evidence contracts.

Any continuation must use a new immutable runtime/manifest identity and may
only carry a hash-verified scored prefix after a separate recovery audit.
