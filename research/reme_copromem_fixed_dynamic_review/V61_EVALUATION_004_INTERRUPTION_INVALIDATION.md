# Evaluation 004 infrastructure-interruption invalidation

`v6_1_exploratory_diagnostic_evaluation_004_clean_restart` is retained as
`INVALID-INFRASTRUCTURE-INTERRUPTION — audit-only`.  Its scientific manifest
SHA-256 is `ee17600bf551972848e659b371dd34912b73f8fbf0ebeeb2dbee6e3a726a8290`.

One No Memory artifact is mechanically valid: it has official score 1.0, an
absolute E-backed journal, hash
`dc1b5a848efc9558690e6e589a21448318484c86c334fb8ed5bd17e04854bb6c`, 83 rows,
and frozen registry identity
`09325ae59f351b4b18ae5127a456890c844515b872277ba4c133ffbd9c5c4423`.
It is excluded from all successor state and analysis.

The stop was caused by an external handoff check looking for non-existent
field aliases (`execution_evidence_locator` and `registry_sha256`) instead of
the producer's canonical fields (`execution_evidence_run_relative` and
`execution_evidence_registry_sha256`).  It was not an evidence failure.

ReMe Fixed was interrupted before its scored artifact was durable.  The
append-only ledger has 16 settled executor calls for that trajectory and one
unresolved executor reservation.  No ReMe Dynamic update marker exists.  The
unresolved reservation is retained historical maximum exposure; it is neither
settled nor copied as an active request into evaluation 005.

No evaluation-004 score, partial history, retrieval, lifecycle state, or
memory update is used by evaluation 005.  The predecessor directory is never
edited by this amendment.
