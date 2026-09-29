# V6.1 Semantic Graph Recovery

This is a zero-provider method amendment and recovery audit. It preserves the
terminal v6 recovery unchanged and rebuilds only from the immutable 24 shared
acquisition artifacts identified by manifest SHA-256
`422a45f8925b82dd83287bb10642a857fd3753b77570ccadb069f4ed310ad607`.

## Rule

The frozen public callable registry determines each response-attested event's
role: domain operation, infrastructure/discovery, authentication/runtime
context, or supervisor/control. Only domain operations enter the semantic
projection. Non-domain events stay as value-redacted provenance. Equivalent
domain repeats collapse into a node with multiplicity and event references;
endpoints of distinct directly attested domain dataflow remain separate.

Planning and commit are transactional. A schema must have a domain-only core,
a supported domain terminal effect, complete provenance, and byte-identical
offline retrieval reconstruction. Rejected plans retain their input state.

## Recovery result

The final derived recovery is
`copromem-v6.1-semantic-recovery-003` (local ignored evidence), report hash
`eb8439498017200cc50c92e506c807ccbb448def40d410fecc4974690129217f`.

- 11 schemas committed across six acquisition families; one plan was rejected.
- No committed core contains infrastructure, authentication, or supervisor
  operations, and no committed terminal has any of those roles.
- Every committed retrieval reproduced byte-for-byte from its frozen bank and
  query; fixed-bank retrieval did not mutate semantic state.
- All twelve duplicate commit checks were idempotent.
- No provider, embedding, scorer, executor, or decomposition request occurred.

The complete sanitized, per-schema audit is local under the ignored artifact
directory. It records source trajectory IDs/scores, original and projection
hashes, excluded role-bound nodes, collapsed-repeat evidence, retained domain
dataflow, terminal, support, family, provenance, and retrieval reproduction.

This establishes only semantic-bank admissibility. It is not an evaluation or
an efficacy result. ReMe construction remains intentionally unstarted pending
review of this amended method and recovery.
