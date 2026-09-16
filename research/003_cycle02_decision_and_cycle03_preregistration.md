# Cycle 2 decision and cycle 3 preregistration

Date: 2026-09-16. Branch: `codex/copromem-research-loop`.
Base commit: `18025102c010e85f26b0b3fb1144a1cb684b587e` plus recorded working-tree source hashes.

## Cycle 2: REVISE

The predeclared source collection produced 36 planner/solver rollouts on 12 GSM8K
training tasks: 35 successes and one failure. Two success/failure pairs come from
only **one** independent task. No candidate satisfied the two-source-task gate.
The bank is empty; development, audit, and evaluation calls were consequently skipped.
No gate was relaxed and the final GSM8K test set was not opened.

There were 72 successful physical calls, zero recorded provider failures, and
USD 0.00209930 charged. Model: `mistralai/ministral-3b-2512`; pinned provider:
`mistral`; seed 23; three source rollouts per task; fixed hash selection seed 601,
offset 7. Full configuration is `research/configs/cycle02_induction.json`.

Report: `artifacts/research/cycle02_induction/reports/a7baaf14bbf82925dfbf0d3e1c408e6350be49ce5548c46fd6da4372b8855fa1.json`.

The failed source is `train-2591`, checkpoint
`7f09a8b6af4660b13c59847ca6e4e16e8a06f0bcb0fce87eca16a7e5cd185776`.
Its artifact contains nonempty `operations`, `answer_unit`, and `check` fields,
as do the two successful artifacts. All use object-valued operation entries.
Thus enforcing the old list-of-strings schema would also flag the successes.
An offline build-only signature audit will record whether the current grammar
can distinguish these pairs at all; this is diagnosis, not a new admission gate.

Strongest competing explanations: a near-ceiling model/task slice produced too
few negative examples, or structural fields do not represent the errors that
matter to mathematical task success. This experiment cannot separate those yet.

## Cycle 3: prospective second-backend diagnostic

Before collecting outcomes, retain the same 12 build tasks and reserved disjoint
development/audit/evaluation partitions, same prompts, token caps, restricted
grammar, source-support gate, replay gates, and three rollouts per task.
Change the model/provider to `google/gemma-3-4b-it` / `deepinfra/bf16` and seed 41.
Official endpoint metadata currently lists this route with seed support and
USD 0.05 / 0.10 per million input/output tokens; archive metadata at launch.
Hard cap: USD 0.25 and 400 HTTP attempts. Do not change the route after seeing scores.

Hypothesis: additional outcome variation exposes repeated structural failures
that the current miner can capture. Competing explanation: failures occur in
semantic reasoning while structural signatures remain indistinguishable.

Primary metric remains the number of admitted candidates under unchanged gates.
Secondary diagnostic: number of matched tasks/pairs and their structural signature
collisions. A zero-candidate outcome despite multiple independent failing tasks
would strengthen the case to pivot away from schema-only GSM8K contracts.
Any positive bank must still pass the shared-path static and sham controls;
this diagnostic alone can establish neither superiority nor generalization.

This is a planned model-sensitivity experiment motivated by cycle 2, not a
post-hoc search for the best model. Report both cycles regardless of outcomes.
