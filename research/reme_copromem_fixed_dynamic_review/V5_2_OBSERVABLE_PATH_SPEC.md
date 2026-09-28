# v5.2 observable-path specification

Policy: `observable_supported_path_v5_2`.

A frozen public descriptor declares one ordered path from the content-addressed
`appworld-public-alternative-path-registry-v5_2` registry.  The registry is
built before execution from public OpenAPI metadata only.  Each operation has
canonical operation/slot signatures, app ownership, read/write role, optional
versus required input fields, schema-compatible alternative producers, and
read-to-write public-schema dependency edges.  Alternative producer groups are
not semantic aliases unless public metadata explicitly declares one.

A successful trajectory may promote exactly one path only when every selected
path step has direct durable public operation evidence, all non-public inputs
resolve from an earlier selected public output, and no unsupported operation,
concrete value, private state, or scorer information enters its procedure.

The plan stores the complete raw trace as audit-only evidence, the selected
path/projection audit, and the projected canonical signature. Validation picks
only successful complete paths; commit replays that projection transactionally.
Rejected plans retain the pre-state exactly. Retrieval keys by the same path
signature and must reproduce offline. Fixed state remains immutable and each
Dynamic stream merges only after its scored trajectory is durable.

Before an engineering run, the public path registry, metadata hashes,
normalisation rules, dependency edges, and compatible A/B path descriptor must
be frozen from public API metadata.  The sole declared runtime normalisation
removes local `var_N` bindings and the infrastructure `access_token` argument;
all remaining named public fields must match the frozen schema.  No
execution-derived API guessing is permitted.
