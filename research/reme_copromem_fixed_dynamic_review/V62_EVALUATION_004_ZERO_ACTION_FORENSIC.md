# Evaluation 004 Zero-Action Boundary Forensic

Evaluation 004 stopped after a durable CoProMem Dynamic task batch because a
zero-action, truncation-terminated scored artifact uses the explicit
`canonical-zero-action-evidence-v1` scorer attestation.  The task-boundary
checkpoint writer incorrectly required the ordinary scorer-binding key.

This is a lifecycle integration defect.  The repair accepts the versioned
zero-action scorer identity only when the action count is exactly zero and the
attestation has its registered version and non-empty scorer hash.  All other
missing scorer evidence raises a typed error before plan, validation, commit,
or state mutation.  No default scorer value is synthesized.

The failure occurred while writing the `trajectories_complete` checkpoint,
before semantic planning, validation, commit, or post-state snapshot for the
second task boundary.  Its frozen pre-state is
`1cff4e8192f853d9e835e7e6054346867a7b53584f0c9d61ee13b757885d0b75`.
Read-only reconstruction of the two durable Dynamic artifacts is deterministic
and produces a rejected, non-mutating marker; it does not authorize replay.
