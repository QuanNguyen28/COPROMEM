# Completion audit and next research cycle

Date: 16 September 2026. This is a progress audit, **not** a declaration that the
autonomous research goal is complete.

## Requirement-level evidence

| Requirement | Current authoritative evidence | Status |
|---|---|---|
| Isolated branch; preserve user work; no commits/pushes | Current branch `codex/copromem-research-loop`; HEAD unchanged; protected document hashes match `000_initial_state.md`; no deleted tracked paths | Satisfied so far |
| Shared immutable real-task checkpoints | `checkpoints.py`, paired runtime/tests, 83 saved planner checkpoints across the three cycles and passing artifact audit | Implemented and exercised on GSM8K |
| Static/sham controls and arm isolation | `paired_gsm8k.py`, `contract_runtime.py`, tests and eight paired development continuations | Implemented; small diagnostic only |
| Genuine evidence-based induction | `induction.py`, source matching/veto tests, 72 real source episodes over two backends | Implemented for a narrow structural DSL; zero candidates |
| Independent minimization/admission/ablation path | `induction_pilot.py`, `contract_runtime.py`, unit tests | Implemented and fixture-tested; real runs never reached a nonempty bank |
| Learned scope, retrieval, semantic/stateful constraints | Public benchmark scope and candidate-by-candidate evaluation only | Incomplete; do not attribute synthetic-bank features to the real learner |
| Preregistered cheap pilots; raw costs and negative cases | Configs/cycle records, request/response/cache archives, reservations and settlements | Three paid cycles plus offline audit completed below caps |
| No test tuning; preserve evaluator | New GSM8K cycles use train-derived splits; score/answer extraction shared; AppWorld preflight uses one train task | Satisfied for new work; old inspected test slices are not fresh confirmation sets |
| Current primary-literature audit | `NOVELTY_MATRIX_20260916.md`, linked primary papers/repositories and code inspection notes | Substantial audit completed; novelty is high-risk, not established |
| Approximately six baselines/four families | `BENCHMARK_BASELINE_SHORTLIST.md` | Shortlist completed; broad implementation/reproduction incomplete |
| Strong fair empirical baseline comparison | Mandatory controls in cycle 1; adapted literature baselines explicitly labelled; native scorer fixture only | No published-baseline reproduction or learned-versus-static win |
| Canonical broader adapters | Native AppWorld dependency and state probes in `010_NATIVE_ADAPTER_AND_RESUME_AUDIT.md` | Incomplete; database restore is not a full checkpoint |
| Reproducibility and resumability | Raw hashes/costs audit; changed-provenance resume guard; exact-source snapshots added for new runs | Improved; original intermediate uncommitted source trees were not all archived |
| Defensible quality/efficiency advantage | No qualifying evidence; both real induction banks empty | Not achieved |
| Strongest validated replacement direction | Evidence-backed stateful/effect-validation proposal in `008`; native feasibility observations | Best current hypothesis, not yet validated as the strongest viable method |
| Full detailed English research document | `009_CURRENT_CODE_RESEARCH_DOCUMENT.md` plus dated records and proposal | Delivered as a separate document; originals preserved |

Tests and setup checks do not substitute for the missing empirical/novelty
requirements. The active goal must remain open; there is useful in-scope work and
no established external blocker.

## Cycle 5: canonical stateful checkpoint validation (no model calls yet)

**Question:** can an isolated fresh process reconstruct a saved public action
prefix closely enough to make treatment continuations comparable?

**Hypothesis:** fixed task/seed, identical recorded actions and equal tool access
can reconstruct the relevant environment state, interpreter state and public
observations. Native database-only restoration is not assumed sufficient.

**Strongest competing explanation:** equal public outputs can conceal different
database/random/clock states; a trivial prefix can pass while a mutating prefix
fails. Replaying a prefix can also give one method extra uncounted work.

**Required next work, before paid collection:**

1. Check available container/isolation facilities. WSL with access to the user's
   filesystem is not sufficient for arbitrary model-generated Python. Keep the
   API provider outside the execution worker; mount no `.env` or user workspace
   into the worker. Do not weaken guards to make a smoke test pass.
2. Implement a bounded canonical worker with unique directories and a public-only
   observation/action boundary. Separate evaluator privileges from agent inputs.
3. Save prefix content and expected observations immutably. Replay the same prefix
   into fresh workers and compare public outputs plus harness-only state digests.
   State digests must never become privileged features for the agent/contract.
4. Test empty and mutating prefixes, interpreter variables, explicit clock
   advance, randomness, reset, cross-arm isolation, scorer/collateral invariance,
   timeouts and failed-worker logging. Do not infer correctness from a process
   exiting with code zero or from identical exception strings.
5. Account for prefix reconstruction separately from deployable agent cost, and
   apply it symmetrically. Reject divergent checkpoints before treatment.
6. Inspect official train-family grouping and permitted splits before registering
   a source collection subset. Avoid template leakage as well as duplicate IDs.

**Engineering support criterion:** every declared matching/reset/invariance test
passes on the saved diagnostic cases with guards enabled and no secret exposure.
**Falsifier:** any state mismatch, unexplained scorer difference, cross-arm leak,
silent dropped failure or uncounted asymmetric replay invalidates the adapter.

**Budget:** zero model calls for this cycle. The subsequent real source pilot
requires its own immutable configuration, explicit task-group split, fixed model
and provider, attempt/token caps and maximum USD 0.25 reservation budget (within
the user's USD 5 limit). Do not run a six-baseline/four-benchmark grid yet.

**Research gate after adapter validation:** collect an outcome-independent small
train task stream and determine whether repeated public stateful defects exist.
If useful rules only restate API schemas, if repair effects are unstable, or if
generic retry/static checks explain all benefit, revise or reject that direction.
The goal is evidence for a method, not success of the adapter itself.
