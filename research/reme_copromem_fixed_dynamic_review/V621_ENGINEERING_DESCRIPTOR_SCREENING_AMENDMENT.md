# v6.2.1 engineering descriptor-screening amendment

Status: preregistered protocol/metadata-interface amendment.  It does not
alter the v6.2.1 retrieval policy, accepted memory banks, model route, scorer,
or any historical evaluation.

## Reason

The permitted held-out inventory exposes task identifiers only.  It cannot
establish task-conditioned compatibility before a task's agent-visible public
instruction is read.  This amendment separates that metadata limitation from
the retrieval method and introduces a custody-bound, zero-provider screen.

## Stage A: public-ID custody freeze

Before an instruction is read, the implementation constructs the complete
`test_normal` pool, removes every hard-exposed or custody-ambiguous identifier,
and sorts the remainder lexicographically.  The committed protocol records the
candidate-list and exclusion-set hashes, source and policy identities, frozen
registry identity, descriptor extractor identity, descriptor schema, and this
selection rule:

1. scan candidates in canonical order;
2. select the first two `compatible` descriptors;
3. select the first subsequent `incompatible` descriptor;
4. never replace a selected item after execution or outcome observation.

An insufficient complete screen is a NO-GO; it is not repaired by task
shopping.

## Stage B: isolated public descriptor extraction

The extractor may read only the public information supplied to the executor
before action execution: instruction, app descriptions, callable/tool
metadata, and the frozen registry.  It is prohibited from calling a provider,
model, executor, scorer, lifecycle service, embedding route, or task API.  It
does not persist instructions, values, answers, state, responses, histories,
or scorer data.  Its sanitized record contains identities, hashes, public app
and operation classes, compatibility features/rejections, and selected schema
identities only.

Every screened ID is engineering-exposed, including IDs not selected for the
run, and is excluded from later confirmatory allocation.

## Stage C: engineering execution

Only after the completed screen deterministically produces two compatible
items and one subsequent incompatible control may the 30-trajectory,
five-arm, two-trial run be frozen.  The run remains compatibility-conditioned
engineering validation, not unbiased efficacy, superiority, or generalization
evidence.
