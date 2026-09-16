# A hand-coded selector reaches the quality ceiling on the available control pairs

Recorded 2026-09-16 on `codex/copromem-research-loop`, HEAD
`18025102c010e85f26b0b3fb1144a1cb684b587e`.

**Decision: REVISE. Do not use this fixed-pair sample to demonstrate learned
activation superiority.** A simple risk-reduction selector obtains every
reachable beneficial outcome and avoids every harmful edit among these eleven
pairs. The quality oracle cannot do better on the same supplied branches.

This is the result of the [saved-branch diagnostic](060_SAVED_BRANCH_SELECTION_DIAGNOSTIC.md).
Unlike the earlier warning-only report, it recombines actual original/edited
native outcomes at common checkpoints. It still is NOT a new online policy
experiment, a held-out comparison or a learned contribution. The selector was
hand-coded in this research-agent loop after the development outcomes were known;
no human-subject authoring time or effort was measured.

## Exact pairing and complete denominator

The fourteen-record source contains eleven edited branches and three factual
controls. Every edit is paired with its factual control using the same
checkpoint, origin episode and target action index. Entire worker requests match
after replacing ONLY that action: task, seed, other settings, prefix and saved
future actions are identical. The existing state-comparison function verifies
each pair's saved pre-action state. Worker/program identities and native scores
are checked against the frozen source cases. No benchmark action or scorer runs.

All ten Cycle-13 variant/origin records and the one Cycle-18B edited record are
retained. They represent **two known scenarios and three checkpoints**, not eleven
independent tasks. The same factual control is reused for alternative edits;
aggregate counts weight those alternatives and must not be treated as population
success estimates or an eleven-task deployment evaluation.

`F/T` below are the saved native outcomes. `Keep` selects the factual branch;
`Edit` selects the supplied edited branch. All-clear and risk-reduction decisions
use the same public-only findings for both programs.

| Original row -> edited row | Original / edited native | All-clear | Risk reduction | Risk-reduction outcome | Native API entries original / edited |
|---|---|---|---|---|---:|
| 10 -> 0 | F / F | Keep | Keep | F | 37 / 31 |
| 11 -> 1 | T / F | Keep | Keep | T | 33 / 11 |
| 10 -> 2 | F / F | Keep | Keep | F | 37 / 30 |
| 11 -> 3 | T / F | Keep | Keep | T | 33 / 10 |
| 10 -> 4 | F / T | Edit | Edit | T | 37 / 53 |
| 11 -> 5 | T / F | Keep | Keep | T | 33 / 11 |
| 10 -> 6 | F / T | Edit | Edit | T | 37 / 53 |
| 11 -> 7 | T / T | Keep | Keep | T | 33 / 33 |
| 10 -> 8 | F / F | Keep | Keep | F | 37 / 30 |
| 11 -> 9 | T / F | Keep | Keep | T | 33 / 10 |
| 12 -> 13 | F / T | Keep | Edit | T | 151 / 185 |

## What is selected, and what is learned?

The **all-clear** reference requires an original warning and no detected warning
after editing. It rejects the playlist repair because the unchanged first-artist
consumer warning remains, thereby missing a real local benefit.

The stronger **risk-reduction** reference requires a strict subset of the
original name/pagination/consumer warning reasons, no new reason and no unknown
pagination status. It accepts that partial repair: the single-page risk goes
away while the consumer risk does not worsen. This is a manually specified
selection rule, not an induced contract or a proof that arbitrary warning
reductions improve task outcomes. These particular outcomes are measured in
the saved native branches; generalization remains untested.

The comparison therefore closes an important loophole: beating an unnecessarily
strict all-clear policy on the playlist case would not establish learned value,
because a simple, more competent manual partial-repair policy already selects it.

## Aggregate offline policy outcomes

Beneficial/harmful flips are relative to selecting the original branch for each
pair. The oracle uses the native labels, chooses success where possible, and
keeps the original on ties; it is not an executable public-information method.

| Selector | Edits selected | Native successes / 11 | Beneficial | Harmful | Remaining quality ceiling gap | Sum of selected native API entries |
|---|---:|---:|---:|---:|---:|---:|
| No-op | 0 | 5 | 0 | 0 | 3 | 501 |
| Always-edit | 11 | 4 | 3 | 4 | 4 | 457 |
| Manual all-clear | 2 | 7 | 2 | 0 | 1 | 533 |
| Manual risk reduction | 3 | 8 | 3 | 0 | 0 | 567 |
| Quality oracle, keep-original ties | 3 | 8 | 3 | 0 | 0 | 567 |

These are exact recombinations of verified fixed-branch outcomes, not newly
executed learned-policy rollouts. They identify the local activation value a
hand-coded rule can already obtain under the saved open-loop continuation.
The effect of induction, memory retrieval, a live recovery agent or adaptive
future actions remains unmeasured.

The risk-reduction selector adds **66 native API-log entries** relative to no-op
across this repeated-control denominator. The smaller always-edit count is
accompanied by four harmful flips and is not an efficiency win. Log entries are
not OpenRouter calls, USD or latency; no conversion to those units is justified.

Zero *quality* headroom does not prove zero efficiency headroom. An outcome-aware
quality-then-log-count oracle could reduce 567 to 547 entries by selecting the
cheaper three F/F branches, including two new NameError branches. This simple
arithmetic follows the per-pair table, but is not a validated safe policy or an
efficiency result. It illustrates why native binary success and a call-count
proxy alone are insufficient safety/cost criteria. The reported primary oracle
remains the pre-specified keep-original-on-ties oracle, unchanged.

## Scope outside the eleven pairs

The complete existing Cycle-17B/Cycle-18B effect-report inventory has 31 edits,
of which the Cycle-18B passing edit is already in this sample. The other **30
records are explicitly inventoried, not evaluated by this selector**. They
include four F/T edits and zero T/F edits; all four benefits are at the same
previously repaired aa8502b r0 episode, at actions 10, 11, 12 and 13.

No public presence is borrowed across checkpoints and no unsupported names are
fabricated as absent. Some inventory records share an observed checkpoint, but
the full edited-program public inputs and B/manual decisions were not part of
the frozen fourteen-record experiment. We do not call the entire historical
corpus solved by this control or claim those records provide independent task
transfer. The quality-ceiling conclusion applies only to the eleven evaluated
pairs. Seven factual cells in the earlier 48-cell diagnostic are controls, not
additional repair opportunities.

## Leakage, engineering verification and cost

- The activation function accepts only `original` and `edited` risk summaries,
  each consisting of canonical warning reasons and an unknown flag. It rejects
  outcome/ID fields. Native outcomes and costs enter only the evaluation layer;
  the oracle is explicitly label-privileged.
- Human/agent-authored rule development had access to these known-build results.
  This is disclosed post-hoc development exposure, not a blind evaluation claim.
  No reserved task was read or selected.
- The whole candidate and the same inspection information are available to each
  selector. No policy generates its own edit or changes downstream actions. This
  does not price the archived donor acquisition cost or measure authoring effort.
- Nine focused fixtures check partial repair, no improvement, newly introduced
  risk, unknown cases, schema rejection, immutability, paired harmful flips,
  oracle arithmetic and missing-cost handling. Full suite: **473 tests pass**;
  new-code scoped lint passes. These are engineering checks, not research wins.
- **0 new model calls, 0 native executions, 0 sandbox runs, 0 new experimental
  Ruff invocations, USD 0 new API cost.** Local analysis time is not claimed free.
  Paid totals remain USD 2.85687245 settled / 2.85793295 charged-reserved.

Evidence store: `artifacts/research/post22_saved_branch_selection`.

| Artifact | Content digest |
|---|---|
| Complete report | `ddf9e80dbe78f7c935abb63c31fbaba975fcf339d7e1bb9a889029b5c87f48cb` |
| Frozen source/specification/test snapshot | `51fa5eedc06c8dab18f28c9ff2d80ff3e0d3d5f999b0a28fe1c5603297d0c8c2` |
| Original static report | `44089b0c774a60e7f942675dbccb0b77e3d2e81f6fdeb68af51205a8383dfe8a` |
| Original manual report | `f0f6d56e74663d66cf6c297f889c63efdf6b632a049c5f403f2fd5e48af7ba71` |

The exact configured-key scan of the new script, tests, specification, result,
new evidence store and root files (excluding `.env`) found zero matches and zero
unreadable paths in 11 files / 118,980 bytes. Its dated audit is
`7c316ee40c6eb1d9a0a9d6e79f39c7989c41688b69a22e566eb4ded1c2e625b9`.
This is an exact-current-key check of those scopes before this paragraph, not
a general or encoded-secret scan. Both original research-document hashes and
the branch HEAD remain unchanged.

## Consequence

The current known-build records cannot support a positive quality-superiority
test for learned selection of these same edits: the manual reference reaches
the ceiling. Do not spend model calls fitting a selector to them and then call
its consistency an efficacy advance. Do not weaken the manual reference to
manufacture headroom.

Further work would need to change a scientifically meaningful variable: produce
better repair candidates, demonstrate benefit on genuinely new failure contexts,
or measure a real efficiency/authoring-effort advantage at matched quality and
safety. Each requires its own evidence and fair control. The available evidence
supports local repair content and manual activation, not a uniquely useful
learned verifier or a validated novel pivot. The strict decision remains
REVISE; the paused proposal run remains unexecuted and the research goal remains
unresolved. No commit, push, reset or deletion occurs.
