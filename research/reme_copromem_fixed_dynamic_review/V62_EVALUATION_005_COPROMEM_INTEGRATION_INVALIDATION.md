# Evaluation 005 CoProMem integration invalidation

Status: `INVALID-METHOD-INTEGRATION: no CoProMem guidance was retrieved or injected.`

Evaluation 005 is immutable audit evidence.  Its scores remain usable only to
explain this integration failure; they are not a CoProMem-versus-baseline
comparison and must not be used for efficacy, superiority, or generalization
claims.

## Read-only findings

The frozen run contains 120 CoProMem retrieval records: 92
`empty_public_query` records and 28 `specific` records.  The legacy boundary
evaluated 1,916 schema candidates.  Every candidate was incompatible and every
selected schema ID was null.

The stored query and schema operations share the same public canonical
namespace (`apis.<app>.<operation>`) and the same callable-registry identity.
The v6.1 semantic records inside the legacy `contrastive_v6_schemas` container
are valid committed semantic schemas; they were not mistaken for candidate or
quarantine records.  The first rejecting legacy predicate for every evaluated
candidate was terminal-effect absence from the query.  For specific queries,
the predicate then also required every learned prerequisite to be mentioned
literally in the task wording.  The runner did invoke its CoProMem callback;
it supplied an empty string, so the CoProMem and No Memory initial prompts were
byte-identical.

This is an integration/method-interface failure, not evidence that the frozen
schemas are ineffective.  Dynamic commits can add retrieval-visible schemas,
but the legacy predicate prevented practical retrieval of them.

## Versioned repair

`copromem-v6.2.1-task-conditioned-retrieval` derives only public
terminal-effect evidence from the agent-visible instruction and the frozen
callable registry.  It treats response-attested schema prerequisites as learned
procedure content rather than hidden wording requirements.  It retains exact
registry identity, terminal compatibility, public-app relevance, positive
support, committed-schema visibility, deterministic tie-breaking, full
per-candidate provenance, and byte-for-byte offline reproduction.

The repair is separately versioned.  The retrospective replay is diagnostic
only: it does not alter Evaluation 005, recompute scores, inject guidance into
history, or make a causal counterfactual claim.

See `v6_2_evaluation_005_copromem_v621_retrospective.json` for sanitized,
content-addressed root-cause and replay evidence.
