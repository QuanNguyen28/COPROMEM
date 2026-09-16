# Cycle 22 decision: REVISE, not GO

Recorded 2026-09-16 after the user's strict-gate instruction. This closes the
research decision around the already registered experiment; it does not change
its primary metric. The registered **component** gate passes: retain configuration
B. The proposed learned-contract contribution has **not** passed an efficacy gate.

No completed experiment was restarted. The existing 28 original/repeated checker
record pairs and 20 isolated-runtime process records were verified from their
saved outputs and current frozen-source hashes. No new model, checker or native
benchmark execution was required for this decision report.

## Complete per-record result

A = unchanged Ruff F821 with the shared framework name declared. B = the same
checker plus names actually observed present at the exact public checkpoint.
`Clear` means no F821 warning, not semantic correctness. The task column is the
**previously saved native outcome**, not the result of a checker intervention.
Rows use the exact 0-based order of the frozen cycle-22 protocol.

| Row | Source variant / origin | Reported missing name | A | B | Saved task |
|---:|---|---|---|---|---|
| 0 | C13 `025e6a9e6cbd7fa3`, o0; producer removed | None | Clear | Clear | Fail |
| 1 | Same variant, o1 | None | Clear | Clear | Fail |
| 2 | C13 `340499df9a57f2f8`, o0 | `page_limit` | Warn | Warn | Fail |
| 3 | Same variant, o1 | `page_limit` | Warn | Warn | Fail |
| 4 | C13 `3b6e3851403f4a10`, o0 | None | Warn: `liked_songs` | Clear | Pass |
| 5 | Same variant, o1 | `liked_songs` | Warn | Warn | Fail |
| 6 | C13 `45c299c43e68a9e6`, o0; retained repair | None | Clear | Clear | Pass |
| 7 | Same variant, o1 | None | Clear | Clear | Pass |
| 8 | C13 `ac7826fc42ad8709`, o0 | `page_index` | Warn | Warn | Fail |
| 9 | Same variant, o1 | `page_index` | Warn | Warn | Fail |
| 10 | `c21-control-00`; original aa8502b r0 | None | Clear | Clear | Fail |
| 11 | `c21-control-01`; original aa8502b r1 | None | Clear | Clear | Pass |
| 12 | `c21-control-02`; original b7a9ee9 r0 | None | Clear | Clear | Fail |
| 13 | `c18b-edit-02`; bound b7a9ee9 repair | None | Clear | Clear | Pass |

For C13, o0 is aa8502b r0 before action 13; o1 is aa8502b r1 before action 10.
Rows 12--13 use b7a9ee9 r0 before action 19. Full cell IDs and all diagnostics
remain in the original report, not replaced by this abbreviated table.

| Aggregate local NameError classification | A | B |
|---|---:|---:|
| True warnings | 5 | 5 |
| False warnings | 1 | 0 |
| Missed reported NameErrors | 0 | 0 |
| Correct clear decisions | 8 | 9 |
| Eligible records / excluded records | 14 / 0 | 14 / 0 |

Both detect the actual missing name in all five error records. B changes exactly
one decision, row 4, where the binding already exists. **Checker-level beneficial
flips: 1; harmful flips: 0; unchanged: 13.** These are correlated development
records, not fourteen independent tasks.

**Task-level beneficial/harmful flips: not estimated.** No checker-triggered
recovery was executed. Avoiding a false warning could avoid an unnecessary repair,
but that counterfactual was not measured. The earlier two local native repairs
are not evidence that a learned verifier selected them better than a static one.
There is no admitted stateful learned contract or comparable learned-arm prediction
vector here; its incremental effect is unmeasured, not proved equal to zero.

## Five decision questions

### 1. What remains unsolved?

**Procedural incompleteness despite executable, name-correct code.** Rows 0, 1,
10 and 12 are clear under B but fail the task: four of nine checker-clear
records. The source/repair contrasts concern missing or incomplete collection
production, including paginated retrieval. F821 cannot establish that the
requested collection has been covered and correctly consumed. This is an
observed limitation of this rule, not proof that all static verification fails.
A competent human-written pagination/coverage check is a necessary competitor.

### 2. What extra information can learning use?

**Currently, no exclusive additional runtime evidence.** The proposed monitor
would inspect code and the same public presence information. Cross-episode
failure/repair evidence could teach relations among task requirements, API
pagination semantics, collection production and consumption. F821 does not
interpret those relations, but a stronger static control could use the same
public information. That difference is learned decision logic, not privileged
access to facts unavailable to the baseline.

Any future task instructions, API specifications or response observations must
be shared across arms. Hidden namespace values, evaluator bodies and final
labels cannot become runtime features. Presence alone does not reveal collection
contents, completeness or correctness. A rule that just checks for a loop is
not a validated semantic contract.

### 3. Is a minimal held-out causal test possible?

**A valid design exists; it is not executable as a learning-value test yet.**
First freeze one genuinely induced semantic/activation rule and a competent
manual procedural control. Neither is presently validated. The planned
known-build Cycle-23 consistency test is not a substitute.

A bounded design would use the four already reserved development scenarios,
first variant and three fixed seeds: twelve planned episode opportunities.
Before outcomes, select the first public, scope-eligible producer/consumer
boundary that B clears; keep episodes lacking a boundary in the coverage report
and do not replace them after inspecting labels. This targets residual failures,
not all tasks. These are scenario-disjoint from induction, not final-test data.

At each selected immutable checkpoint, construct **one common repair candidate**
without either verifier's decision or explanation. Evaluate original and repaired
branches using identical saved downstream actions and the unchanged native scorer.
No-op, always-repair, B-plus-manual-semantic and B-plus-learned activation policies
then choose between those same two outcomes. Charge every policy the same repair
generation/inspection budget, even if it declines repair. This isolates selection
value from different repair generations, extra calls and downstream randomness.

This is an open-loop activation test, not full adaptive multi-agent recovery.
The existing harness is sufficient in principle; no new general platform is
justified. Textual/success-only and broader efficacy comparisons remain necessary
before publication, but are not silently claimed by this small falsification test.

### 4. What exactly falsifies it?

For that fixed candidate and slice, define G as learned-success/static-failure
cases and H as learned-failure/static-success cases, using the **strong manual
static control**, not F821 alone. Primary effect is `(G-H)/N` on eligible records.

Proposed go/no-go thresholds, declared here before such a test:

- Do not promote unless G is at least 2 across at least 2 scenarios and H is 0.
- If at least 2 beneficial repair opportunities missed by the static policy
  exist across 2 scenarios, but `G-H <= 0`, the candidate's claimed incremental
  selection benefit fails this gate. If H is positive, its declared zero-harm
  pilot safety requirement also fails.
- If there are insufficient eligible boundaries or reachable beneficial repair
  opportunities, the test is uninformative/underpowered, not a negative result
  for every possible learned contract. Do not fill the sample post hoc.

This is an operational falsification/promotion rule, not a population-level
significance claim. A tiny null result cannot disprove all possible formulations.
Identical static/learned decisions give no incremental value on the tested slice;
matching a manual checker is not an authoring-effort win without measuring effort.

### 5. Continue or pivot?

**REVISE the formulation; do not scale or resume the current known-build
predicate-fit cycle as evidence of progress toward efficacy.** Retain B and the
existing replay/runtime implementation. Drop name-presence correction and
generic syntax-count fitting as the novelty nucleus.

Further work is justified only around a concrete learned semantic/scope decision
that could differ beneficially from the competent manual control, followed by
the single bounded causal test above. If no such rule/observable distinction can
be specified, or the evaluable test fails its incremental-benefit gate, pivot
away from the learned-verifier quality claim instead of adding infrastructure.
The strongest retained empirical asset is context-bound local procedural repair;
it is a possible basis for a repair-selection pivot, **not an already validated
novel contribution**. No alternative pivot is currently proved superior.

## Leakage, execution and cost audit

- All fourteen records are retained; context is bound to exact original
  episode/planner/checkpoint state. Queried coverage is complete. Unknown names
  were never silently replaced by absent ones.
- Checker inputs contain program text and permitted public bindings only.
  Local labels come from actual reported NameError outputs; native final scores
  are audit columns, never checker inputs. No reserved task instruction or
  evaluator body was added to this experiment.
- All 28 original checker processes have identical saved repeats. Frozen source
  hashes and all twenty saved sandbox fixture processes verify without restart.
- Cycle 22: 28 original + 28 repeated checker processes, plus 2 metadata and 2
  toy-fixture processes; **0 model calls, 0 new native benchmark executions,
  USD 0 new API cost**. The isolated-runtime preflight, completed later and
  retained under its original Cycle-23 directory, used 20 constructed sandbox
  processes and 14.327 recorded seconds; also 0 model calls and USD 0 API cost.
  It is not retroactively relabeled as native Cycle-22 evidence.
- Prior paid totals remain USD 2.85687245 settled / 2.85793295 charged-reserved.
  Local compute is not zero-cost merely because API USD is zero. Checker latency
  was not separately measured; no value is invented.

Authoritative checker report:
`44089b0c774a60e7f942675dbccb0b77e3d2e81f6fdeb68af51205a8383dfe8a`.
Exact-repeat/independent-count audit:
`29a92ada86516322f635750c6d685e2dc6d6190cc59834f5f5471b071cf16fa5`.
Isolated-runtime preflight:
`d2061cd58e5acc90e5354af9d3ad3ca4cf234218ee1a1d9a0c26ee2b935948ed`.

Cycle-23 preparation predates the user's latest constraint and is preserved,
but further work on it is paused. Its new generation-runner draft has not been
run, tested or frozen; its output store does not exist. No paid proposal has
been sent. No files were discarded, and no commit, push, reset or merge occurred.
