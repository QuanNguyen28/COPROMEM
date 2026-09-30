# CoProMem v6.2.1 task-conditioned retrieval

## Scope

This is a versioned retrieval-interface repair for the v6.1 semantic bank.  It
does not modify the bank, induction method, AppWorld executor, official scorer,
or ReMe lifecycle.

## Query and compatibility

Before execution, the boundary derives a public query from the current visible
instruction, public application descriptions, and the frozen callable-schema
registry.  Registry-declared aliases are normalized to the canonical
`apis.<app>.<operation>` namespace.  A candidate must be a committed v6.1
semantic schema with the exact frozen registry hash, a registry-declared
terminal effect supported by the query, relevant public application evidence,
and at least two positive supporting trajectories.  Candidate/audit containers
are never retrieval-visible.

The query need not state every response-attested prerequisite.  Those steps
remain schema-derived guidance, not a condition manufactured from task text.
Schemas without sufficient public terminal-effect evidence return empty
guidance.  The method never uses generic guidance to force a non-empty prompt.

## Guidance and provenance

Guidance is deterministically rendered from the selected schema's required
public operations and typed public constraints.  It contains no task values,
credentials, IDs, hidden state, scorer data, responses, or task-specific rules.
Failure support may add an operation-specific public-precondition warning, but
cannot replace a success-supported procedure.

Every retrieval records query derivation, pre-state hash, candidate features,
first rejection reason, selection, support counts, guidance hash, prompt
injection hash, and a full provenance hash.  `reproduce_retrieval` fail-closes
on state, query, registry, schema, or provenance tampering and reproduces the
exact guidance bytes offline.

Fixed retrieval is non-mutating.  Dynamic retrieval reads its durable per-task
pre-state; only a valid task-boundary commit can affect later retrievals.

## Prompt and ReMe instrumentation

CoProMem callback guidance, upstream ReMe retrieval, and actual prompt-memory
injection use distinct typed provenance fields.  The ReMe observer only hashes
the unchanged response from the pinned upstream `get_memory` call; it neither
rewrites that response nor changes the model-visible prompt.

## Fail-closed conditions

Unknown operations, non-registry aliases, malformed schemas, insufficient
positive support, terminal mismatch, invalid Dynamic prefix state, ambiguous
ties, and any offline reproduction mismatch produce either explicit empty
guidance or a typed error before dispatch.  They never silently fall back to a
generic memory.
