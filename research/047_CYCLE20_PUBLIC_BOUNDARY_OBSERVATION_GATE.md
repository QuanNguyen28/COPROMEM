# Cycle 20: public read-only boundary observation gate

Registered 2026-09-16 after the complete cycle-19 REVISE result, before any new
probe implementation or native execution. Branch/HEAD, source code, native
worker/evaluator and all earlier protocols remain unchanged. Zero model calls
or new external API USD are authorized for this gate. No contract is admitted.

## Hypothesis and exact purpose

An ordinary agent-visible code action can export a bounded binding envelope at
the existing saved code-action boundaries without changing supported execution
state, tool effects or eventual native outcome. If this fails, do not feed
harness namespace information into a learner as a substitute. Diagnose or revise
the public observation interface separately.

This is an observation/adapter gate, not a new verifier, a method comparison, or
a claim that collection completeness or applicability can be learned from name
availability. Final-task outcome labels remain distinct from local violations.
The existing boundary is an executor-to-code-tool action boundary; introducing
this envelope does not create a new agent-to-agent handoff or establish a MAS-
specific effect. Any later MAS claim requires an explicit common workflow design.

## Fixed three source checkpoints

Use the saved source checkpoints already bound by cycles 13 and 18:

1. c11-aa8502b_1-r0 immediately before its original action 13.
2. c11-aa8502b_1-r1 immediately before its original action 10.
3. c11-b7a9ee9_1-r0 immediately before its original action 19.

All are existing build evidence, not reserved or unseen data. The first two
include the exact-code conflicting-outcome example from cycle 19. The third
is the new repair's original source boundary. No new source task, model,
instruction body, seed, donor or successful trajectory may be selected after
observing probe output.

For each boundary, select names **mechanically from public source code**: the
union of all `ast.Name.id` identifiers in the original and canonical repaired
target programs. For the two old boundaries, also include the already tested
initializer-deletion program with AST
`3b6e3851403f4a101337fc8401784c933f2dd7fd3214d56f306bc9054058ee9e`.
Remove Python builtin identifiers and the framework receiver `apis`; sort and
deduplicate. This generic selection receives only source text, not task ID,
score, public error names, namespace or task instruction. Preserve empty name
sets if any; do not replace them with a hand-selected useful variable.

## Public envelope and noninterference constraints

The probe is a single ordinary public code action that reports, for each selected
name: presence, an allowlisted builtin type category, and length **only** for
exact builtin list/tuple/dict/set objects. Do not export scalar values, string
contents or lengths, dictionary entries, object representations, tokens or
credentials. Other types receive an explicit unsupported category. An absent
name is a normal observation, not an infrastructure failure.

Use no API requests, hidden evaluator data, worker-side namespace extraction,
model call, filesystem read or external service. Do not execute user-defined
`__len__`, property, iterator or formatting methods. Do not introduce persistent
global helper variables or mutate existing bindings. Generate the query from
the name list, save its exact source and parse only its public result. If sandbox
restrictions, builtin shadowing or a supported-state mismatch prevents this,
retain the failure and REVISE; do not silently substitute privileged access.

The evaluator/harness may inspect complete supported state **for noninterference
auditing only**, under the same separation as earlier checkpoint experiments.
Its hidden values must never be copied into the public envelope or classifier.

## Fixed arms, execution and metrics

At each checkpoint run two arms through a fresh live stream and a separate full-
prefix replay: (a) the unchanged original saved action sequence; (b) exactly one
probe inserted immediately before the target action, followed by every original
target/future action string unchanged. This gives **six cells, twelve native
executions and twelve native scorers**. Use the unchanged 50-action image,
original source environment seeds and canonical 150-file public bundle. All
selected sequences plus one probe must fit the original action limit; otherwise
record an explicit failed gate, not an unregistered limit increase.

Fresh controls must reproduce original public outputs, errors, completion,
supported final state and native scores. Probe arms must match their own fresh
replay exactly. The supported state immediately before versus after the probe
must match: database hashes, serializable namespace/alias structure, random
state, clock and completion, plus zero new native API-log entries. Source action
history necessarily has one extra probe; remove exactly that inserted item when
checking unchanged original outputs and shifted error indices. All later
supported final state, completion and native score must agree with control.

Record the extra public code action, generated query, raw public result, parsed
envelope, complete process commands/results, checkpoints, replay evidence,
native tool counts and measured time. The inspection is not free compute merely
because no monetary API call occurs. Future baseline and method arms must have
the same envelope and inspection allowance or an explicitly matched alternative.

Primary metric: number of the three checkpoints passing the complete public-
output schema, exact replay and noninterference conditions. **KEEP this bounded
observation interface only if all three pass** and every registered cell is
accounted for; otherwise **REVISE**. Never use whether an envelope looks useful
to change this primary gate. Integrity/infrastructure errors halt for explicit
diagnosis; unsupported observations and absent names remain in the denominator.

Before execution, freeze the implementation, tests, selected public source
identities, exact queries and execution manifest. Unit tests must cover generic
name selection, no scalar/credential export, absent names, exact builtin-type
checks, unsupported/custom objects, no user-defined length invocation, no leaked
helper binding, shadowing/restriction failure, robust output parsing and source
checkpoint binding. Audit all raw native records after completion and retain
failed probes. No new query may be chosen in response to the first native output.

## What this gate cannot establish

A passing probe only makes a small piece of context available through a common
public interface. It does not learn required names, semantic artifact quality,
scope, full collection coverage or a recovery decision. No final test is opened.
The next research protocol must define boundary-specific violation labels and
learn/validate checks separately from source collection, static verification,
recovery, admission and retrieval. The two earlier local repairs and the negative
code-predicate result remain intact. The autonomous research objective is active.
