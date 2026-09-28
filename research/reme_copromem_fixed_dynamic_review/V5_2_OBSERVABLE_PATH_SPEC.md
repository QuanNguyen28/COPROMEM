# v5.2 observable-path specification (not yet executable)

Policy: `observable_supported_path_v5_2`.

A frozen public descriptor declares one or more ordered dependency paths. Each
path contains canonical public operation/slot signatures and explicit allowed
public-input edges. A successful trajectory may promote exactly one path only
when every path step has direct durable public evidence, all edges resolve
within the path or a declared public input, and no unsupported operation,
concrete value, private state, or scorer information enters its procedure.

The plan stores the complete raw trace as audit-only evidence, the selected
path/projection audit, and the projected canonical signature. Validation picks
only successful complete paths; commit replays that projection transactionally.
Rejected plans retain the pre-state exactly. Retrieval keys by the same path
signature and must reproduce offline. Fixed state remains immutable and each
Dynamic stream merges only after its scored trajectory is durable.

Before an engineering run, the public path registry, aliases, dependency edges,
and compatible A/B path descriptor must be frozen from public API metadata.
No execution-derived API guessing is permitted.
