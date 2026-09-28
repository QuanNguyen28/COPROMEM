# v5.1 observable-supported-subgraph method

Policy version: `observable_supported_subgraph_v5_1`. Strict-v5 remains
`strict_exact_v5` and is unchanged.

V5.1 retains a complete normalized trace as local immutable audit evidence,
but projects transferable structure from directly observed public descriptor
steps only. A step must match operation and abstract slots, be ordered as the
descriptor specifies, contain direct public evidence, and have no unresolved
dependency on an excluded helper. Projection uses no provider calls.

The frozen `public-helper-registry-v1` recognizes public API-documentation,
credential-display, login, and completion identities. A helper can be excluded
only when none of its outputs feeds a required descriptor input. Otherwise the
dependent procedure is unresolved and the transaction rejects. Extra observed
operations are recorded as descriptor steps, allowed helpers, unrelated
exploration, unresolved dependencies, or disqualifying unsupported operations.

The transaction is still plan → validate → commit. Rejected plans preserve the
pre-state. Valid plans use descriptor-derived signatures, content-addressed
schema/procedure IDs, offline reconstruction, and idempotent commit.
