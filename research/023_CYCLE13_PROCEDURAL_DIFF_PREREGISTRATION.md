# Cycle 13: evidence-derived statement-block transplant and local reduction

Registered 2026-09-16 before executing any new edited program. Branch
`codex/copromem-research-loop`, HEAD
`18025102c010e85f26b0b3fb1144a1cb684b587e`. Prior goal turn: **progress** (cycle-11
source contrast, cycle-12 checkpoint-controlled cross-over, native ExpeL retrieval
and 164 passing tests). No active Docker worker remains at entry; no blocker.
The research goal is not achieved and the earlier independent-support gate is
not relaxed. Preserve originals, old sources/results and vendor code; no commits.

## Question and competing explanations

Can a generic source-code operator derive a smaller executable edit from the
saved failed/successful final programs, while retaining the failed program's
other behavior, and preserve the successful program's native outcome at both
already frozen build checkpoints?

The retrospective pagination observation motivates the experiment, but **no API
name, task ID, pagination keyword, page size or corrective loop is encoded in
the proposal operator**. Concrete statements and constants must come from the
actual saved donor program. A hand-authored general search operator is not itself
learned; the proposed edit is derived from the recorded pair and effect-tested.
This does not automatically produce a contract, learned scope or admission.

Competing explanations: (a) unrelated changes elsewhere in the donor are needed;
(b) an apparently smaller block depends on accidental persistent variables;
(c) static name analysis misses aliases, mutation or control dependencies;
(d) partial side effects or extra API work masquerade as a clean repair. Native
effect validation and explicit counts, not syntax alone, decide local validity.

## Frozen evidence and selection

Use all mixed-pair endpoints already frozen in cycle-12 protocol digest
`e575d8e9adb8b79fc89b8638697d3cd066254d60d1dd8efe686bc0a9b3b58f3b`
and report `669e67cf8164c3cd4e31d0e029bc3c4069ca26436ff17d9b5ac4cea0956aea5a`.
Currently this is one task and two pre-final checkpoints. Failure/success roles
are determined only by the archived native binary labels. No different episode,
task, seed or API is substituted if proposal or validation fails. Both origin
environment/public/planner checkpoints remain bound exactly as in cycle 12.

No development, audit or evaluation scenario is opened; this is build-data
search. Both origins are from the same task and do not constitute independent
source-task support. No newly proposed predicate may be admitted from this cycle.

## Generic proposal operator, version 1

Parse each saved program without executing it on the host. Candidate anchors
are variable names with exactly one direct, simple, top-level assignment in
each program. For each common anchor (lexicographic order), derive a block that
computes/mutates that binding before later consumers. Method calls on that name
and subscript/attribute writes are conservatively treated as possible mutation;
this is a heuristic name-based analysis, not a sound arbitrary-Python slicer.

Work backward from the last relevant producer/mutation statement, adding earlier
statements whose written names are read by the selected statements. An identical
shared statement prefix can supply unchanged dependencies. Close each selected
set to a contiguous top-level statement span, preserving intervening statements
rather than pretending they have no effect. Replace the failed program's producer
span with the donor's span; retain every other original statement. Skip identical
AST replacements, reject syntactically invalid transplants, deduplicate by AST
identity, and archive all proposals and rejection reasons. No donor-only renamed
downstream variable should be copied unless required by the extracted span.

The operator's language support and limitations must be documented and tested on
neutral authored programs, including renaming the anchor away from benchmark
terms, dependency closure, no-op rejection and preservation of the original
suffix. No fixture success is a native task result.

## Effect gate and reduction

For each initial candidate, execute the same patched program from **both** exact
origin checkpoints with the unchanged cycle-11/12 image, native tools/guards and
evaluator. Each cell has a live pre-action identity check and an independent
fresh-process replay plus native scoring. Original cycle-12 control cells must
first pass a read-only integrity/scorer/database audit. No new model generation
is made; original generation/provenance IDs remain archived.

A candidate preserves the local effect only if every origin has native task
success, a true completion flag, supported state, no new uncaught action error,
and matching replay/evaluator results. Native failure, exception, unsupported
state, timeout or mismatch is recorded, never converted into a success. A
worker/integrity failure stops the cycle for diagnosis; a normal action error
rejects that variant while preserving its observation/native score.

For a passing transplant, attempt deletion of one **top-level donor-block
statement** at a time in original source order. Keep a deletion only if the same
effect gate passes at both origins; restart the scan after an accepted deletion.
Cache previously tested program ASTs. Stop at a deletion fixed point or the
registered cap of **12 distinct edited programs per source pair**, including
initial proposals. Do not silently increase the cap if no edit passes.

This can establish only a tested **single-statement-deletion fixed point within
the extracted block** if every relevant deletion is tested. It is not a globally
minimal program, minimal AST clause, optimal repair, or a proof that pagination
alone caused the difference. Nested-body deletion, substitutions, constants,
semantic-equivalent rewrites and independent-task transfer are outside this
registered search. If capped, report the reduction as incomplete.

## Outcomes, accounting and decision

Primary outcome: number of automatically derived transplants preserving native
success at both origins. Secondary: accepted/rejected reductions, native checks,
completion/error/unsupported states, replay identity, preserved suffix, edited
statement/non-context-AST-node counts, program length and native API log deltas.
Count all simulations and replays; report model cost **USD 0** separately from
local CPU/API-simulation work. Programs may execute different API-call counts;
no quality-cost or equal-compute method superiority is implied.

Budget: at most 12 edited programs x 2 origins x 2 executions = 48 native worker
executions per pair, plus corresponding isolated native scorer invocations.
Same 50-action episode capacity, 15-second/100-API-call/24,000-character per-action
guards and supervised secret-free containers. No real external account mutation,
credentials, paid generation or evaluator modification is authorized/needed.

KEEP only a reproducible local evidence-derived block repair if at least one
transplant passes; REVISE if none passes or the operator/experiment fails its
technical checks. KILL any specific variant contradicted by clean native results,
retaining the full record. No inferred scope or contract admission is claimed.
Even a successful edit must later face strong static/documented completeness
checks, equal-compute recovery and independent source/dev/audit validation.

Store: `artifacts/research/cycle13_procedural_diff`. Snapshot source/configuration
and an immutable copy of this preregistration before execution; write results in
a separate later record so appending outcomes cannot alter the preregistration.
Reject source/evidence mismatch on resume. Partial live episodes are fail-closed
and require explicit recovery audit, not silent repetition.
