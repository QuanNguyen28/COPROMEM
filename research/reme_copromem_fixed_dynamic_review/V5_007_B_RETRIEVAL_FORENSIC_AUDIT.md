# v5-007 B retrieval forensic audit

Classification: **implementation/interface defect**, followed by a strict-v5
task-suitability limitation. This audit made zero provider, model, embedding,
AppWorld, or scorer calls.

## Sanitized decision trace

The frozen public descriptor and B retrieval query had the same signature
digest: `348dea077b9cf7202373e6db54c32c00ab080cb68ff1817d85da9b48d7d2febd`.
The promoted A execution trace had a different signature digest:
`3c80aabc9669bf9a0855a652bf3aa06cb703ad6f1294cb0d8256f23cb2f8978a`.

The committed A schema was `schema_ed463bbee52d89eb`, and it was present in
the B provenance candidate-schema inventory. However, exact strict retrieval
computed `schema_8a5037f881162c29` from the B public/query signature. That
schema did not exist. The first rejecting predicate was therefore
`learning_core_exact_schema_lookup_missing`.

`candidate_scores` being empty is not a second rejection: strict-v5 takes the
direct `LearningCore.retrieve` branch, which performs exact schema lookup and
does not invoke the legacy procedural-memory similarity scorer. Consequently
no learned guidance can be assembled after the exact lookup misses.

## Defect and repair

The task-boundary planner received an empty descriptor from the runner, even
though retrieval was supplied a frozen public descriptor. The old validation
could therefore promote an execution-derived schema without verifying that it
was the same schema retrieval would query. The repair supplies the frozen
descriptor to strict task-boundary construction and requires every scored trace
signature to equal it before a winner can be promoted. It is an exact-match
guard; it does **not** implement the proposed v5.1 observable-subgraph rule.

## Consequence

The repaired strict-v5 mechanism now fails closed for a pair whose public
descriptor cannot exactly predict the eventual observed executor trace. A
fresh strict-v5 task pair must satisfy this exact condition. If no such pair
can be selected from public pre-execution metadata, a separately versioned
v5.1 signature amendment is required; it must be evaluated as a new method,
not silently substituted into strict v5.
