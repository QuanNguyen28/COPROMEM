# CoProMem v6.2 task-conditioned retrieval amendment

v6.2 is a method/integration amendment, not unchanged v6.1.  It derives a
content-addressed `TaskQueryRecord` before retrieval from only the current
public instruction, public app/tool metadata, and frozen callable registry.
The bank, outcomes, scorer, hidden state, task IDs, and prior evaluation data
are not inputs.  Ambiguous public evidence yields an empty query and empty
guidance.

Selection requires registry equality, app compatibility, and that every
required learned operation is present in the task query.  Sorting resolves only
ties among compatible candidates; it cannot select an incompatible first item.
The retrieval provenance binds the task-query record, pre-state hash, selected
schema, candidate scores, and final guidance hash; offline reproduction remains
mandatory.

Fixed and Dynamic own independent deep-cloned semantic states.  Fixed retrieves
only from its immutable initial state and never plans, validates, or commits an
update.  Dynamic freezes one pre-task state for both trials, then transactionally
commits (or rejects byte-identically) after both scored trials.  Restart must
restore the two identities independently and must never replay retrieval or an
update.  A future dispatch is blocked until state hashes, task-query replay,
non-aliasing, cross-domain incompatibility, and empty-guidance behavior pass.
