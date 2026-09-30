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
