# Cycle 20 preflight result and cycle 21 presence-only revision

Recorded 2026-09-16. The preceding goal turn made progress: cycle 19 completed
the fixed predicate diagnostic and changed the next action. The research branch,
original documents, HEAD and native guard policy remain unchanged.

## Cycle 20: REVISE before native execution

The exact worker source frozen in cycle 18 explicitly rejects `globals`,
`locals`, `type`, private attributes and builtin-module access. The unchanged
policy rejects the proposed namespace/type primitives, while accepting an
ordinary named public expression. One fixture confirms these policy results.
This is a concrete limitation missed when registering the full envelope, not
evidence that the six native cells ran or that every possible envelope is
impossible. No guard was weakened and no harness values were substituted.

Decision **REVISE the full-envelope implementation at preflight**. The registered
six-cell/twelve-execution native experiment remains unexecuted: actual native
executions/scorers/model calls/API USD are all zero. No native noninterference
primary result is claimed. The source-policy gate is preserved in
`artifacts/research/cycle20_observation_preflight`:

- Report `843ef9235acc0085a62b563ddb59c3612a684d3d0bec953a18bb182f128f82e3`.
- Source snapshot `5cd12e7fb7da047548523be8c153456aba144de3f715063b9d3e27bbf0c34ac5`.

## Cycle 21 preregistration: a distinct, deliberately limited observation

Before implementation or native execution, register a **presence-only** public
query. It is not equivalent to cycle 20's type/length envelope and cannot satisfy
that abandoned gate. The purpose is narrower but directly motivated: determine
whether ordinary public name references expose the missing-input distinction
seen in cycle 19, while keeping the full contract-learning objective open.
No type, length, contents, scalar values or generalized applicability is inferred.

Keep the exact same three source checkpoints, unchanged 50-action image,
canonical bundle, original seeds and six-cell/twelve-execution/twelve-scorer
control/probe design from [047](047_CYCLE20_PUBLIC_BOUNDARY_OBSERVATION_GATE.md).
Use its same mechanically selected names from original/canonical repaired code,
plus the old initializer-deletion program. No names are chosen from observed
missing-name errors, namespace fingerprints or task outcomes. Names absent at
the checkpoint remain normal outcomes; no selection changes after observation.

For each selected identifier, submit a direct public reference whose value is
discarded inside a lambda; print a fixed name/present-true record. Catch only a
`NameError` from this expression and print the fixed name/present-false record.
Use no exception alias or persistent helper assignment. Never print or format
the referenced object, call its methods, inspect its type, enumerate a namespace
or read any files. An empty name set emits a distinct valid empty marker.

Conservatively reject construction if the public prefix syntactically binds or
deletes `print` or `NameError`, including imports/function names/exception aliases
and capture patterns. This protects the query's control operations on the tested
public-language prefix; it is not a proof against arbitrary compromised runtimes.
The complete generated query must pass the unchanged worker policy and size cap
before execution. Do not truncate the name set or rewrite a rejected query after
seeing native output. Save exact public inputs, name lists, queries and failures.

Validate output with an exact marker/schema/name/order/denominator check. Only
the ordinary public action output may populate the presence envelope. Hidden
state remains exclusively an auditor input. All arms must retain identical
planner/upstream checkpoints and original future actions. The probe adds one
public code action, which must be counted; no model or API tool request is added.

Primary metric remains noninterference: number of three checkpoints passing the
complete exact replay, public-output and unchanged supported state/outcome gates.
**KEEP this presence-only interface only if all three pass and all six cells are
accounted for; otherwise REVISE.** Secondary descriptive result: observed presence
differences at the known conflicting source pair. A useful-looking difference
cannot rescue a failed primary gate or become an efficacy/admission claim.

All 047 state/history/error/tool-count/scorer invariants apply. Unsupported final
state and invalid query output are retained failed gates; integrity/transport
failures halt for explicit diagnosis, not silent restart. Freeze implementation,
tests, source provenance and all queries before the first new native cell.
Audit raw worker/scorer processes, output parsing, unchanged original actions,
post-probe state, complete sample and metrics independently after completion.

Tests must cover arbitrary identifiers, public-only construction inputs, no
credential/object-value export, absent names, no object method invocation,
unchanged global bindings, control-name shadowing, native-policy rejection,
empty and malformed output, duplicate/missing/extra records and source identity.
No method comparison, contract admission, new paid call, new task or reserved
partition is allowed. Original negative findings and the full research objective
remain intact.
