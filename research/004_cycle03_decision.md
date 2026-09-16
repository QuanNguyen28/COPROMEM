# Cycle 3 decision: PIVOT away from schema-only outcome attribution

Date: 16 September 2026. Branch `codex/copromem-research-loop`.
Base commit `18025102c010e85f26b0b3fb1144a1cb684b587e`; exact pre-run source hashes
are saved with the cycle. The original documents and previous conclusions remain intact.

## Observation

Under the preregistered second-backend protocol, Gemma 3 4B produced 25 successes
and 11 failures across 36 rollouts of the same twelve build tasks used in cycle 2.
Five tasks provided ten matched success/failure pairs. No structural candidate
was generated; the admitted bank is empty. No development, audit or held-out
evaluation calls were made. No final test data was opened.

All ten pairs have identical structural feature signatures. Six pairs also have
identical **full planner artifact content**, despite different solver outcomes.
Changing from the near-ceiling Mistral model therefore produced substantially
more negative outcomes without making the current grammar discriminative.

Report: `artifacts/research/cycle03_induction/reports/2bc8e0a2a8eaec418946c0336434730f707202a268c8ca21300ff926eef569e2.json`.
The `observability/` directory contains append-only v1 and v2 audits; v2 adds
full-artifact equality without changing previous results.

## Cost and failure accounting

Configuration: `google/gemma-3-4b-it`, pinned `deepinfra/bf16`, temperature zero,
seed 41, three rollouts per task, 220 planner / 320 solver token caps.
Predeclared cap: USD 0.25 and 400 HTTP attempts.

There were 72 completed generations and 74 HTTP attempts: two requests retried
once before succeeding. Completed-generation usage reports total USD 0.00153115.
Including the two conservatively retained ambiguous-attempt reservations, the
ledger totals **USD 0.00259165 charged or reserved**. It would be misleading to
report the lower number as the fully reconciled bill. No terminal generation
failure occurred. Seventy-one generations stopped normally; one solver was truncated.

Across cycles 1–3: 198 completed generations, USD 0.00515617 in reported successful
generation costs, and **USD 0.00621667 charged or conservatively reserved**.
These are research-pilot costs only, not historical repository costs.

## Failure inspection, not post-hoc rescoring

- `train-4400`: a nonempty typed plan computes 40% of five miles as 2.5; the
  failed final answer is 140 rather than 130. Structural validity cannot check that arithmetic.
- `train-2460`: two outputs give 32000 rather than 320; unit conversion matters.
- `train-5677`: three outputs give 5/6 **hours**, while the dataset gold is 50
  **minutes** and the question leaves the output unit implicit. The repository's
  scalar exact-match scorer counts these as failures; they are not unambiguous
  evidence of incorrect mathematical reasoning. Scores were not changed.
- `train-6199`: one solver exhausts its output cap and has no parseable final answer.

The original GSM8K [evaluation code](https://github.com/openai/grade-school-math/blob/master/grade_school_math/dataset.py)
uses answer-marker extraction and exact matching. Our `FINAL_ANSWER`/Decimal
extractor is a documented harness adaptation, not literally that native function.
Any future unit-aware metric must be predeclared and applied to every arm; never
retrofit it only to improve the proposed method's score.

## Strongest alternative explanation and limits

One narrow task slice, only two backends, and small samples do not refute all
procedural contract learning. Different downstream random draws can produce
opposite labels for identical artifacts. A handoff can change failure probability
without deterministically determining success. The source label is task outcome,
not a verified annotation of a causal handoff defect.

The defensible conclusion is narrower: **this outcome label plus this structural
representation is inadequate on these recorded GSM8K traces**. More failures
alone did not fix it. An empty bank is the correct result under the stated gates,
not evidence that abstention is a learned policy improvement.

## Decision: PIVOT

Retain the checkpoint, budget, replay, controls, safe DSL and audit infrastructure.
Stop promoting schema-only GSM8K induction as the main empirical story. Do not
scale the four-benchmark matrix or lower admission thresholds to create a bank.

The leading research direction is **effect-validated contracts over observable
stateful tool transitions**, with explicit separation between:

1. a suspicious handoff or violated condition;
2. a downstream task failure;
3. a repair that actually changes the downstream outcome for the better.

Train an intervention rule from paired continuation outcomes, not by treating every
failed episode as a defective schema. The proposed primary target is net repair
benefit at matched cost, including harmful flips on benign cases. AppWorld is the
leading candidate environment, conditional on a validated common adapter and
access only to its allowed development material. This remains a research direction,
not a newly established method, novelty claim, or empirical win.

## Immediate next gate

Before building a large adapter, test an offline repair-benefit diagnostic on the
already saved paired cycle-1 continuations. It should make the distinction between
schema failure prediction and observed intervention value explicit, use zero new
API calls, preserve every row, and reject a gate with only harm/no benefit.
The diagnostic cannot establish transfer; it only checks whether the next learning
target is well specified. Literature already covers counterfactual diagnostics,
runtime enforcement and learned repair/localization, so the remaining gap must
be stated narrowly and tested rather than presumed.
