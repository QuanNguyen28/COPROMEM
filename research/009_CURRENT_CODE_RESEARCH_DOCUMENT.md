# CoProMem / CoProCon: current code and research evidence

Date: 16 September 2026. Language: English.

This is a new research-branch document, not a replacement for the preserved files
in `docs/`. It describes the implementation and evidence available after cycles
1–4. The dated records remain authoritative for each experiment. The proposed
next formulation is specified separately in
[008_PIVOT_RESEARCH_SPECIFICATION.md](008_PIVOT_RESEARCH_SPECIFICATION.md).

## Executive conclusion

The repository is an experimental framework for executable procedural contracts
at fixed agent handoffs. It now supports a substantially more defensible real-task
evaluation protocol than the original independent-arm GSM8K runner. It does **not**
yet demonstrate that learned contracts improve quality, efficiency or human
authoring effort beyond strong static controls.

There are two different implementations, not one uniform mature system:

1. A historical synthetic workflow with domain-written join-cardinality logic,
   simulated role behavior, contract storage, retrieval and budget enforcement.
2. A new real-model research pipeline with immutable planner artifacts, generic
   structural predicate mining, independent replay gates and common execution
   paths for static and induced checks.

The second pipeline found an empty learned bank in both registered induction
diagnostics. That is a valid negative result. The recommended decision is to
retain the protocol and pivot the representation/target toward **effect-validated
public stateful handoff contracts**. This direction is motivated, not validated.

## 1. What the method is supposed to do

A fixed workflow has a producing role and a consuming role. The producer emits an
artifact such as a plan. A contract checks a condition on that artifact before
the consumer proceeds. If the condition is violated and the contract applies,
the workflow returns the artifact to its owner for a bounded repair.

The desired research contribution is not merely calling a verifier. It is learning
which small conditions are useful, where they apply, and whether intervention
actually improves the downstream outcome without excessive harm or cost.

This is distinct from selecting agents, changing teams or routing models. Those
ARCO-style choices should remain fixed in the main CoProCon comparison. Otherwise
team-selection effects could be mistaken for procedural-memory effects.

The original CoProMem idea of remembering corrective procedures is still visible,
but the current executable unit is a **contract**, not a stored full trajectory
or a free-form reflection. The repository name remains `copromem`; some research
documents and descriptions use `CoProCon`. Neither name implies empirical maturity.

## 2. Repository architecture

| Layer | Principal modules | Actual role |
|---|---|---|
| Historical synthetic world | `types.py`, `synthetic.py`, `workflow.py` | Typed join tasks, observable artifacts, simulated planner/solver/reviewer behavior |
| Historical contract bank | `contracts.py`, `synthesis.py`, `bank.py`, `replay.py` | Domain-written contract proposal, scope/veto, simulated replay, storage and retrieval |
| Historical experiments | `experiment.py`, `tiny_experiment.py` | Controlled feasibility fixtures and synthetic comparisons |
| Real task I/O | `real_gsm8k_experiment.py`, `paired_gsm8k.py` | Dataset parsing, planner/solver prompts, answer extraction, common scoring and paired schema diagnostics |
| Reproducibility | `checkpoints.py`, `providers.py` | Frozen artifacts, request cache, route configuration, bounded transport and cost ledger |
| Genuine structural learner | `induction.py`, `induction_pilot.py` | Build-only matched contrast, restricted predicates, development minimization, audit and frozen evaluation |
| Shared treatment runtime | `contract_runtime.py` | Identical static/induced checker and recovery implementation |
| Evidence inspection | `structural_audit.py`, `intervention_audit.py`, `artifact_audit.py` | Observability, harmful/beneficial flips and saved-archive integrity |
| Baseline/adapter feasibility | `reproduction_probe.py`, `appworld_preflight.py` | Bounded native probes, not published-score reproductions |

The old synthetic `ContractBank` and the new `InducedContract` are different
representations. Features in the former must not be attributed automatically to
the latter. In particular, a validated multi-contract real-task retrieval policy
has not been demonstrated.

## 3. Historical synthetic implementation

The toy problem concerns joins that should preserve row semantics versus
intentional expansion. Public inputs include join keys, actual cardinality,
expected rows and intent. These quantities are part of the synthetic environment;
they should not be confused with information an arbitrary real benchmark exposes.

The planner may omit cardinality/rationale information. The solver may ignore
the plan. The reviewer may detect a mismatch. Behavior is driven by configured
simulation probabilities, not by real LLM cognition. Contracts use known domain
logic to check required plan information and exempt intentional expansion.

The historical bank admits contracts using simulated replay gain, a harmful-flip
cap, transfer success and counterexample-veto accuracy. Retrieval filters by
admission, interface and scope, ranks by recorded benefit and estimated read size,
and obeys storage/read/verification budgets. Its costs are simulation accounting,
not measured OpenRouter invoices.

Reproducing 81.25% success for both contract and static-verifier arms establishes
that the software behaves as the fixture defines. It does not establish automatic
discovery, superiority over static verification or real-world generalization.

## 4. Why the original real-task result needed revision

The original real GSM8K experiment generated planner outputs separately for each
arm. An observed answer difference could therefore come from a different upstream
plan rather than the tested memory/contract intervention. The apparent learning
step also admitted a predefined schema using aggregate observations; its decisive
logic was manually specified.

The new real experiment saves one public planner artifact for each task/replicate.
Every intervention starts from that same artifact. Gold answers remain in the
evaluation dataset and are not placed in checkpoints or prompts. The unchanged
answer extractor/scorer is shared by all arms.

This fixes an important causal confound, but it does not make distinct downstream
LLM prompts deterministic. Provider seeds, repeated runs and paired uncertainty
remain necessary. A shared checkpoint is a necessary control, not a complete
causal identification argument by itself.

## 5. Immutable checkpoints and saved generations

`PlannerCheckpoint` stores a task identifier, public question, split, family,
replicate, canonical artifact content and generation identifier. Its digest
identifies the content. Access returns a reconstructed copy, preventing ordinary
cross-arm mutation through a shared mutable dictionary.

`RunStore` validates record paths and writes records once. Repeating the same
write is accepted only when content agrees; a conflicting write is rejected.
Stored artifacts and calls can be audited against their hashes. These hashes
detect accidental corruption; they are not signatures authenticating an archive
against an adversary who rewrites every hash and record.

`GenerationService` keys its cache on the effective request, including namespace,
model/provider settings, system/user prompts, decoding caps and seed. Identical
effective requests within a replicate reuse one recorded draw. This prevents a
no-op method from looking different solely because it sampled a second response.
Cache reuse is not counted as a fresh independent observation.

Physical collection calls and hypothetical per-arm logical calls are reported
separately. The planner is physically generated once but contributes its logical
share to each deployable arm's cost. Treatment prompts with different lengths or
activation rates can have different actual costs even under identical caps.

## 6. Genuine induction as currently implemented

### 6.1 Evidence and matching

Each `HandoffEvidence` record contains an interface, public context, artifact,
task/checkpoint identity, build partition, execution context and observed final
task success. Candidate proposal reads build records only. Successful and failed
examples must match the task, interface, public context and execution settings.

The default source support is at least two independent matched tasks. Multiple
rollouts from one task do not satisfy this requirement. Duplicate evidence is
deduplicated. The later v2 miner also considers successful build artifacts that
have no matched failure when vetoing a proposed invariant. Ignoring those
counterexamples would make the learner too permissive.

### 6.2 Executable language

The language has four operators: `present`, `nonempty`, `type`, and `list_of`.
Paths are discovered from observed fields, with shallow nested-object traversal.
Checks distinguish booleans from numbers and treat whitespace-only strings as
empty. There is no arbitrary `eval`, synthesized Python checker or hidden answer
lookup in this language.

A clause must hold on all relevant source successes and fail on negatives from
enough independent matched tasks. This is structural invariant mining. It cannot
express arithmetic correctness, causal dependencies, API-state transitions or
semantic equivalence of two plans. Calling it a general program synthesizer would
overstate the implementation.

Scope is public categorical context. The current real GSM8K runner supplies the
benchmark name; it does not establish meaningful semantic scope learning. The
owner is the planner and the recovery route is return-to-planner. Those choices
are fixed implementation design, not learned routing.

### 6.3 Development, audit and admission

Candidate ranking uses build evidence only. The runner bounds the number of
candidates before inspecting development outcomes. Greedy clause deletion tests
whether a clause can be removed while retaining the declared development benefit
and harm gates. This is empirical greedy minimization, not proof of a globally
minimal causal rule.

The selected candidate is replayed on disjoint development tasks and independent
audit tasks. The default engineering gate requires two source tasks, four
development tasks, two audit tasks, at least one beneficial development flip,
positive net development gain, zero harmful flips in development/audit and no
provider failures. All source/development/audit task IDs must be disjoint.

These small thresholds are **smoke gates**, not calibrated population guarantees.
The audit set is independently selected benign-development evidence, not a
comprehensive annotated boundary-case benchmark. Final-test evaluation must not
be used to choose clauses, scope, thresholds or candidate rankings.

An empty proposal/admitted bank stops the downstream evaluation stage. The runner
does not invent a default contract or weaken the admission threshold to produce
positive numbers. This is exactly what happened in cycles 2 and 3.

## 7. Runtime and control arms

The real induction runtime supports the following comparisons:

- **No memory:** consume the unchanged checkpoint with no injected memory.
- **Success-only memory:** inject one source-success artifact at the solver stage.
  This is a deliberately simple adaptation, not a sophisticated retrieval method.
- **Textual rule:** present the candidate predicates as passive advice.
- **Matched sham retry:** activate on the candidate's violations but ask for a
  generic regeneration instead of targeted violation feedback.
- **Static verifier:** human-written checks on `operations`, `answer_unit` and
  `check`, using the same predicate runtime and repair pathway.
- **Learned contract:** check the induced predicate set and return violations to
  the planner for bounded targeted repair.
- **Clause deletions:** remove components of a frozen learned contract; deleting
  its only clause corresponds to no intervention.

The origin label and evidence provenance are not injected into the repair prompt.
An induced and a static copy of the same executable clauses therefore produce
the same effective request. This is a direct test of implementation fairness.

The historical paired-schema runner has a different `copromem` arm: it is
explicitly labelled the earlier observationally admitted, hand-written schema.
Its results must not be called results of the generic learner.

One limitation remains: the induction runner declares a fixed evaluation-arm
order. No learned evaluation was reached in these runs, but a future larger run
must preregister randomized/counterbalanced order to assess service drift. The
earlier paired-schema runner already tests deterministic arm-order invariance
with cached effective requests.

## 8. Metrics and their interpretation

Task quality is the benchmark's unchanged score. A beneficial flip changes an
incorrect no-intervention continuation into a correct one; a harmful flip does
the reverse. Net gain is beneficial minus harmful flips on matched checkpoints.
Task-clustered bootstrap is used in the paired schema diagnostic so two replicates
of one task are not treated as two independent tasks.

The code also records trigger coverage, recovery/schema pass, calls, tokens, USD
and available latency/metadata. A recovered schema is not necessarily a recovered
task. Verifier failure-prediction precision/recall use baseline task failure as a
proxy label; they are not accuracy against gold causal handoff-error annotations.

Costs include raw completed generation usage and conservative reservations for
ambiguous failed HTTP attempts. The provider layer reserves before every attempt,
including retries, and stops at configured monetary/attempt limits. Unexpected
actual overruns are recorded before further calls are blocked, including on
restart. HTTP failures are preserved without response bodies or API secrets.

The pilot provider used pinned routes and no fallback. A seed and model name do
not guarantee deterministic or permanently version-identical model execution;
actual response metadata remains necessary for reproducibility claims.

## 9. Observed evidence

| Cycle | Design | Main observation | Decision |
|---|---|---|---|
| 1 | Four train-derived development tasks, two replicates, shared planner checkpoints | No memory 8/8; static 7/8; sham 7/8; historical contract not admitted and exactly no-op | KEEP protocol, not a learning claim |
| 2 | Mistral source collection, twelve build tasks × three rollouts | 35/36 successes; one matched source task; zero candidates | REVISE |
| 3 | Registered Gemma sensitivity diagnostic on the same twelve build tasks | 25/36 successes; five matched tasks; ten structurally identical success/failure pairs; zero candidates | PIVOT representation/target |
| 4 | Offline repair-effect audit of all eight saved cycle-1 development checkpoints | Static and sham each activate four times, with zero beneficial and one harmful flip | REVISE policies; no new API cost |

Six of the ten Gemma matched pairs had identical **full** planner artifacts, not
just identical structural signatures. The same visible handoff can therefore
precede different downstream outcomes in this corpus. Final failure is not a
deterministic label of a defective planner artifact.

One task's exact-match failures involved hours versus the evaluator's expected
minutes, with implicit units; another solver response was truncated. These cases
remain scored by the original evaluator and are disclosed as interpretation
limitations, not retrospectively rescored to improve the result.

The three paid cycles collected 198 completed generations in 200 HTTP attempts.
Settled generation usage totals USD **0.00515617**; the ledger totals USD
**0.00621667** including two conservatively reserved ambiguous retry attempts.
Each cycle used a USD 0.25 cap, below the user's USD 5 maximum. No population
superiority claim follows from these small diagnostics.

The alternative explanations are explicit: the first model supplied too few
failures, the second supplied more failures but no structural distinction, the
DSL is limited, some errors arise in the consumer, and exact-match labels can
conflate format/unit issues with reasoning errors. The evidence rejects a narrow
schema-only configuration; it does not prove all procedural learning impossible.

## 10. Novelty and comparative evaluation status

The [primary-source novelty matrix](NOVELTY_MATRIX_20260916.md) documents close
overlap with contrastive experience learning, workflow memory, learned skills,
runtime enforcement and counterfactual agent diagnostics. Broad claims such as
“first success/failure procedural memory” or “first executable agent contract”
are not defensible from this audit.

The six research-baseline candidates are ExpeL, Agent Workflow Memory,
ReasoningBank, CONTRAMEM, Skill-Pro and AgentSpec, in addition to the mandatory
causal controls. AppWorld, WorkArena++, SWE-bench and ALFWorld are the four
benchmark-family candidates. These are reasoned shortlists, not four finished
adapters or six reproduced papers. See the
[baseline/benchmark record](BENCHMARK_BASELINE_SHORTLIST.md).

ExpeL and AWM vendor checkouts were restored at their original pinned commits.
An AWM native scorer passed an authored scoring fixture, which verifies scorer
behavior only. The ExpeL native entrypoint probe found missing dependencies in the
current environment. No published baseline score has been reproduced. Existing
common-harness ExpeL/AWM/CRITIC variants remain labelled adaptations.

Skill-Pro's inspected implementation uses action log probabilities in its
historical selection surrogate. Replacing this with a generic LLM judge because
the chosen API lacks those probabilities would materially change the method and
must not be described as exact reproduction.

## 11. Why the stateful pivot is the next hypothesis

The promising question is whether a public stateful boundary exposes a repeated
condition for which a specific repair has positive downstream effect. Candidate
proposal can use contrast, but admission should target paired intervention value,
not assume every failed final answer indicts the preceding artifact.

The prospective object remains compact and executable, with applicability,
predicates, responsible owner, recovery and provenance. New stateful predicate
primitives, effect estimation, calibrated harm control and transferable scope
are not implemented claims. A strong static verifier with the same runtime must
remain the primary control.

AppWorld preflight tests native state handling using authored actions on one
lexicographically selected train task, with no LLM calls or ground-truth solution
access. Native database restore must be distinguished from interpreter, clock,
random and tool state. Its Windows release-specific SIGALRM failure is recorded;
Linux feasibility is a separate engineering check. Neither setup success nor
reset success is a learned-method result.

The detailed hypotheses, falsification criteria, information restrictions and
next experimental design are in the [pivot specification](008_PIVOT_RESEARCH_SPECIFICATION.md).

## 12. Reproducibility, preservation and current phase

All work is uncommitted on `codex/copromem-research-loop`, originating from
`codex/empty` at `18025102c010e85f26b0b3fb1144a1cb684b587e`. Original documents are
preserved and their hashes recorded. No commit, push, merge or pull request was
made. New records and reports are separate from historical results.

The local suite currently has 71 passing tests; Ruff lint and formatting checks
pass. Tests cover checkpoint identity/mutation, no-op equivalence, arm isolation,
leakage, predicate execution, serialization, admission, costs/retries, archive
integrity and supervisor error logging. They establish software properties, not
scientific efficacy. Isolated native benchmark dependencies are not required by
the lightweight unit suite.

For runnable commands and artifact navigation, start at [research/README.md](README.md).
Use new cycle IDs/directories for changed experiments. Retain rejected candidates,
negative runs, preregistrations, raw outputs and cost reservations. Final-test
content must not become development evidence.

**Current phase:** mechanism validation and evidence-backed formulation pivot.
**Not finished:** real learned benefit, meaningful learned scope/retrieval,
calibrated harm control, broader canonical adapters, full baseline reproduction,
cross-benchmark confirmation and AAMAS submission readiness.

## Later same-day implementation appendix: stateful adapter foundation

Cycle 5 added `stateful_adapter.py`, separate Docker execution/evaluation/oracle
entrypoints, a train-only ground-truth-excluding exporter, an explicit public
observation allowlist and a full tested-state prefix comparator. These extend the
experimental infrastructure; they do not implement a validated new memory method.

Four repeated authored-prefix fixtures now cover empty state, mutation/randomness,
Unicode and an observed API error followed by recovery. The native scorer is
separate from the execution worker. A privileged official reference solution
passes 5/5 checks but is explicitly excluded from learning and method comparison;
its scenario group is excluded from future sampling.

The Linux-amd64/Python-3.12 image now has an 80-package hash-locked dependency
recipe. A rebuilt image reproduces the earlier mutating-state fingerprint and
native score. The local suite has grown to 94 passing tests; no new paid model
calls were used. See [the complete cycle-5 record](012_CYCLE05_SANDBOX_AND_NATIVE_SCORER.md)
for raw artifact locations, isolation settings, remaining supported-state limits
and the next source-collection gate. The research objective remains open.

## Later same-day implementation appendix: live source pipeline

Cycle 6 adds a live, fixed planner/executor source collector. It does not yet add
a stateful learned-contract treatment. The following distinction is important
when reading the code or describing the current method in a paper.

`stateful_stream.py` owns one bounded, network-free Docker process per episode.
An initial request identifies the train task, environment seed and optional
recorded action prefix. The worker then accepts one Python program at a time,
returns a frame, and retains its native interpreter between actions. Every frame
is bound to the hash of the complete action prefix. Closing the episode persists
process output, final request and final supported-state evidence; failures retain
partial evidence instead of inventing a completed run.

`stateful_source.py` takes a registered scenario-group split and runs two fixed
roles. The planner sees a bounded public history and emits a short plan object.
The executor sees that same history plus the plan and emits code. Public API or
syntax errors enter the next normal planning step; an error does not terminate
the baseline automatically. The process stops at the declared horizon, public
completion flag, provider failure or infrastructure failure. Only the unchanged
native evaluator determines task success after the episode closes.

The collection saves three related but different identities. The environment
prefix hash identifies task, seed and actions. The public-context hash identifies
the context shown before planning. The immutable generation IDs and source-step
record identify the actual planner artifact and consumer request. The public
context hash alone is **not** a unique planner-artifact checkpoint: different
planner draws may share it. A future treatment comparison must bind the exact
planner artifact and generation along with the environment prefix, rather than
assuming equality merely from a common task or public context.

The worker frame contains harness-only database, namespace, clock and randomness
evidence. These fields cannot enter prompts through the explicit public
allowlist. Independent prefix reconstruction and scoring are research-only
operations; they are not rollback tools given to an agent. Unsupported namespace
objects or mismatches make an episode ineligible for induction, while the episode
and its cost remain in the collection denominator. Supported-state equality is
bounded evidence, not a general Python-equivalence theorem.

`research/scripts/audit_stateful_source.py` is a separate offline audit. It
reconciles generation hashes, parsing decisions, public contexts, source-step
actions, before/after live frames, ledger settlements and optional paired native
state checks. Its syntax diagnostics distinguish exceptions from call-free
expressions; neither is a substitute for native task success. This audit makes no
LLM calls and cannot create a learned contract from a failed corpus.

The live diagnostic passed its replay and scorer checks. The extended unit suite
has 113 passing tests, including public-only context, disjoint scenario selection,
ordinary baseline recovery and descriptive syntax auditing. The registered
source pilot and its later result record must be consulted for actual outcomes;
unit tests alone establish no research advantage.

Important remaining limits are deliberate prompt/history truncation, a restricted
action language, incomplete mid-episode crash recovery, and no stateful learned
bank/admission/comparison implementation. Completed episodes and exact model
requests can be reused under the recorded provenance; partial live episodes
currently fail closed and require audited reconstruction. The
[public-interface audit](014_APPWORLD_PUBLIC_INTERFACE_AUDIT.md) also identifies
onboarding and output-format weaknesses relative to the official minimal agent.
Fixing such common infrastructure is necessary baseline work, not new procedural
memory and not a scientific win.

## Later implementation/evidence appendix: source cycles 6--8

The raw-code public-onboarding-v2 interface is now implemented without replacing
the frozen v1 prompts. Parser compatibility decisions are explicit and audited.
Across successive fixed-sample AppWorld source cycles, syntax improves but native
success remains 0/8 in each cycle. All 24 completed live/replay score pairs from
cycles 6--8 agree. There is still no stateful learned bank or learned-versus-static
comparison; the implementation must not be described as empirically validated
semantic contract induction.

The new [cycle-8 report and cycle-9 preregistration](018_CYCLE08_RESULTS_AND_CODER_PREREGISTRATION.md)
give exact source counts, costs, model/provider changes and interpretation limits.
The next source run uses a code-specialized backend without changing the fixed
workflow or selected tasks. Configurable finite positive price ceilings feed both
provider filtering and pre-attempt budget reservations; old configurations retain
their prior default ceilings. The full unit suite at registration has 137 tests.

An independent, zero-model-call context diagnostic is implemented in
`research/scripts/audit_context_visibility.py`. On cycle 8, 105/120 decision
boundaries contain a truncated visible history item, 9/120 omit earlier history,
and 28 actions exactly repeat the preceding program. Its derived report is
`artifacts/research/cycle08_appworld_source/context_audits/650e682ce3f9de4360ece22e9ebb546d2ab1f9a5bc30dd6e98af54268eb3a7de.json`.
These counts motivate a baseline-context audit but do not prove causation or
identify effective learned predicates. Two new fixture tests check the diagnostic
without modifying runtime source during the paid run.

The [separate ExpeL reproduction record](019_EXPEL_NATIVE_REPRODUCTION_PROGRESS.md)
tracks isolated native dependency work. Earlier prompt adaptations remain labelled
as adaptations; obtaining an official checkout and a compatible environment does
not retroactively make them paper reproductions. Original research documents and
all earlier negative results remain unchanged.

## Latest same-day evidence appendix: cycles 9--10 and ExpeL

The [cycle-9 result and cycle-10 local gate](020_CYCLE09_RESULTS_AND_RUNTIME_GATE.md)
are complete. Cycle 9 produced zero native successes in eight fixed build episodes
with the coding backend; seven were replay-eligible, one was excluded for an
unsupported infinity-valued namespace entry. It made 234 calls for USD 0.19375710.
The original exclusion and all negative results remain unchanged.

The subsequent zero-model-call runtime version explicitly encodes signed infinity
but still rejects NaN, advertises a bounded 50-action capacity, and validates the
requested horizon against the actual running image before any paid call. A
25-action live/fresh-prefix fixture and the exact historical excluded prefix
both reproduce their tested state and native scores. Historical public outputs
and database state remain unchanged. These are bounded engineering findings, not
a general checkpoint proof, learned-contract efficacy or a new source success.
All 143 unit tests pass, with clean lint/format checks.

The [ExpeL native environment](019_EXPEL_NATIVE_REPRODUCTION_PROGRESS.md) now
builds with explicit dependency adaptations. Its unmodified training, induction
and evaluation CLIs initialize; six parser/rule-update fixture checks pass. A
failed authored expectation exposed a multiline parsing quirk and is retained,
not hidden by editing the baseline. No actual native task/model/embedding result
or published score has been reproduced.

The current research status remains **baseline/workflow validation and bounded
runtime support**, with an implemented narrow structural learner that yielded
empty real banks and a proposed stateful effect-validation direction. A competent
common workflow, nonempty evidence-derived stateful bank, strong static/equal-
compute comparison, held-out transfer and novelty/efficacy confirmation remain
required. Nothing in these latest results establishes submission readiness.

## Later evidence appendix: cycle 11 and actual native retrieval

[Cycle 11](022_CYCLE11_RESULTS_AND_CROSSOVER_PREREGISTRATION.md) is the first
stateful source run with a usable same-task outcome contrast: one native success
among eight episodes, one mixed build scenario, eight matching replay/scorer
pairs, and USD 0.44051750 measured cost. Its 50-step capacity was exercised by one
episode, still unsuccessful. The 64,000-character versioned public presentation
retained every historical entry without truncation at all 167 boundaries. It
made 334 completed generations, all with `stop` finish reasons, and had 46 native
uncaught action errors. These results supersede the earlier all-failure source
status, not the absence of an admitted real bank.

The two contrasting episodes have different prior trajectories/planners, so their
outcome difference is not yet a paired treatment estimate. A zero-paid-call
cross-over has been registered: retain each exact pre-final environment and
planner checkpoint, then execute each saved final program without regenerating
it. This tests a whole-program effect only. Pagination differs between programs,
but is already public static knowledge; neither its causal role nor a novel
learned verifier follows from inspecting the difference. One supporting source
task still fails the earlier independent-support admission requirement.

[ExpeL](019_EXPEL_NATIVE_REPRODUCTION_PROGRESS.md) has also progressed beyond
imports/parser tests. An immutable, hash-verified local all-mpnet-base-v2 model
feeds the unchanged upstream native FAISS retrieval path. Seven authored checks
pass, including current-task exclusion, length filtering and shortest-example
selection. This fixture bypasses environment/LLM initialization and uses a stated
word-count budget stub. Native rollout, insight generation, production tokenizer
wiring, paper-score reproduction and fair AppWorld adaptation remain incomplete.
Original `docs/` files and all earlier records remain unchanged.

The registered cross-over is now complete, with [the appended result](022_CYCLE11_RESULTS_AND_CROSSOVER_PREREGISTRATION.md):
from either exact origin checkpoint, the saved successful final program passes
all four native checks and the failing program passes only three. One rescue
and one reverse degradation reproduce in independent replays. This identifies
a local whole-program effect, not a specific pagination clause or learned
verifier. The successful program incurs 23 additional native API log entries
versus seven, so there is no efficiency claim. All 164 host tests pass. The
scientific bottleneck is now minimal procedural-difference induction plus
independent scope/effect validation beyond a strong static control; the narrow
GSM8K structural bank is still empty and no real stateful bank is admitted.

## Latest evidence appendix: automatic local procedural difference

[Cycle 13](025_CYCLE13_RESULTS_AND_RESEARCH_STATUS.md) implements an evidence-
derived producer-block transplant, not a manually supplied pagination repair.
`BlockTransplant` is immutable and records both source-program digests, the shared
binding, source/donor statement spans, retained donor statements, preserved
prefix/suffix AST identities and the generated program. A generic name/dependency
heuristic proposes edits; exact-origin native effect tests validate them.

One proposed block replaces a single request with four donor statements while
leaving the failed program's artist-following suffix intact. It reproduces native
success at both frozen source checkpoints. Four single-top-level-statement
deletions are rejected. One deletion works in only one history because it relies
on an existing variable; the second history prevents a false simplification.
Five variants, ten cells and twenty native executions are archived, with no paid
model call. Proposal/search regeneration and checkpoint/replay/native-score
integrity pass a separate audit. The full suite now passes 197 tests.

This is the first validated automatically derived **local program repair block**
in the stateful branch. It remains unadmitted: no learned verifier, generalized
scope, retrieval policy or held-out contract benefit has been demonstrated.
Single-statement deletion irreducibility is not global/semantic minimality.
More API work is measured, not hidden. Traditional delta debugging and program
repair overlap now appear explicitly in the novelty audit; transplantation plus
tests alone is not claimed as a new contribution.

Baseline progress also includes [ExpeL native ALFWorld execution](024_EXPEL_ALFWORLD_NATIVE_GATE.md).
On one hash-selected training fixture, reset and three neutral actions produce
identical public feedback/native rewards in two isolated containers. Initial
library-mapping failures were preserved and fixed through a scoped native temp
mount, without changing vendor code or AppWorld policy. Current native data and
dependency adaptations are disclosed; no model-backed task-solving, insight
learning or published-score reproduction is newly claimed. The primary next
bottleneck is independent source support and fair scope/transfer validation.

## 2026-09-16 update: independent-source extension failed its contrast gate

[Cycle 14](027_CYCLE14_RESULTS_AND_NEXT_SOURCE_DECISION.md) tests that bottleneck
on four new, hash-selected, previously unallocated training scenarios. The new
selection mode pins and regenerates the old allocation; no reserved group or
task variant is moved into build. The fixed team, model, seeds, prompts, native
runtime, horizon and context settings remain unchanged from cycle 11.

The eight episodes yield four native successes but zero mixed-outcome scenarios:
two tasks succeed twice, two fail twice. Seven replays are eligible. The eighth
contains unsupported `re.Match` namespace state; matching saved scores and
fingerprints do not override the fail-closed exclusion. Native scoring remains
unchanged. Total acquisition cost is USD 0.925044, 434 calls/attempts, with no
unsettled attempts. Historical context is omitted at 39 of 217 boundaries.

The preregistered decision is **REVISE**, not KEEP based on the secondary success
count. The automatic all-pair screen produces no new repair proposal. The old
local repair remains supported on one task, without admitted scope or transfer.
The host suite passes 212 tests; these tests validate infrastructure rather than
the north-star research claim. The result document retains every failure, exact
evidence digest, preservation check, cost and reviewer objection.

The targeted literature search also corrects an omitted context-aware contrast
comparator, AutoGuide, and adds ERL as a single-trajectory acquisition alternative.
See the updated novelty matrix and explicitly revised priority shortlist. The
next source diagnostic should preregister bounded reflection-assisted retries
using public traces and binary build outcomes, not hidden evaluator details.
This remains a proposed collection procedure, not a method win or completed
experiment. Final comparisons must retain strong textual, static and equal-
compute controls and shared source information.

## 2026-09-16 update: reflection source diagnostic remains insufficient

[Cycle 15](030_CYCLE15_RESULTS_AND_SOURCE_REVISION.md) implements the proposed
bounded source-feedback procedure and completes all eight retries. The critic
receives only the fixed original replicate's public trace and binary outcome;
raw notes and downstream contexts are provenance-bound and independently audited.
The fixed role/model/runtime policy otherwise remains unchanged.

The result is 3/8 native successes and 8/8 eligible replays, but **zero new mixed
scenarios** among seven opportunities. It therefore receives REVISE under its
frozen primary gate. Four retries exhaust the horizon. Cost is USD 1.0771182,
544 completed calls, no unsettled attempts. Across all 24 old/new episodes, only
the original aa8502b scenario remains mixed; the new donor produces no new edit
under the existing final-action operator. There is still one unadmitted local
repair, no independently supported scope and no held-out learned-method advantage.
The host suite now passes 233 tests; software checks do not change this conclusion.

The next source route inspects official non-oracle training agent archives under
a separately frozen public-file/replay gate. Metadata confirms that archive
versions differ; older test-only output is excluded, while a newer archive lists
all eight build tasks. No task bodies have yet been inspected. Source-policy,
demonstration and native-version differences must be audited before donor use.

[ReasoningBank's official source and source-function fixtures](029_REASONINGBANK_OFFICIAL_SOURCE_AUDIT.md)
also clarify adaptation dependencies and cache lifecycle behavior. Toy embeddings,
bypassed initialization and a non-native dependency image are explicit; no
end-to-end reproduction or retrieved-memory quality is newly claimed.

## 2026-09-16 update: offline source evidence and broader boundary alignment

The [cycle-16 public-source extraction and local replay](037_CYCLE16_RESULTS_AND_ALIGNMENT_LIMIT.md)
are now complete. Exactly 32 preregistered public log/version files were read;
archive DB/evaluator bodies and other-task/split bodies remain excluded. A separate
bounded 100-action runtime gate preserved the historical 50-action runtime.
All eight unedited archived programs were executed twice and natively scored;
all replay audits pass. Four succeed locally and one independently selected
build task, b7a9ee9_1, becomes mixed for the first time. This supports retaining
the offline source route, not claiming original-policy reproduction or a memory win.

Source-policy provenance discloses a human-written worked example and unknown
historical acquisition costs. Public outputs differ from the archive, so local
repeatability must not be called historical output reproduction. No new model
calls/API charges occur. All subsequent methods must share the same source corpus.

The exhaustive final-action screen over 32 sources yields no new proposal. A
separately registered [all-boundary revision](038_CYCLE17_ALL_BOUNDARY_SCREEN_PREREGISTRATION.md)
examines every one of 1,323 action pairs. It produces 34 provenance records and
26 distinct target-boundary/program interventions, including coverage of the new
task. Unsupported syntax, donor errors, duplicate programs and nulls remain saved;
the complete screen regenerates from frozen source evidence. This establishes
syntactic coverage only. The [all-26 saved-continuation effect test](039_CYCLE17A_RESULT_AND_EFFECT_PREREGISTRATION.md)
is now running with four factual controls and no model calls. Until it completes
and is independently audited, the project still has only the one old validated
local repair, no learned verifier/scope, no admitted bank or held-out method gain.

The full host suite passes 278 tests. Static/equal-compute comparisons, successful-
origin harmful-flip checks, independent support for the same abstract rule and
group-disjoint transfer remain necessary; two unrelated local repairs would not
by themselves satisfy a two-task contract admission threshold.

## 2026-09-16 update: complete all-boundary effects reject independent repair coverage

[Cycle 17B](041_CYCLE17_EFFECT_RESULT_AND_BINDING_FAILURE.md) has completed all
four factual controls and all 26 distinct interventions. The independent raw-
process/checkpoint/scorer audit passes for 60 native executions and 60 scorers.
There are four passing edits, all at different boundaries of the old aa8502b
episode, and **zero independently repaired new task IDs**. The preregistered
decision is REVISE. Each passing edit adds sixteen native API-log entries, so
the result does not establish quality-cost superiority.

Fourteen edited actions fail with a missing donor input name; all six new-task
edits are affected. This is a concrete construction defect, not proof that merely
renaming those inputs will solve the tasks. The retrospective diagnosis labels
its use of harness name availability and does not feed hidden values into a
method. A separately preregistered public-code-only binding/output-closure
revision is the next experiment; no new model calls are needed for its first gate.

There remains one unadmitted local procedure and no independently supported
verifier/scope, bank retrieval benefit or held-out comparison with strong static,
textual and equal-compute controls. The complete suite passes 280 tests; these
software checks do not alter the scientific conclusion. The [AgentSpec source/
parser audit](040_AGENTSPEC_PINNED_PARSER_AND_ENFORCEMENT_AUDIT.md) adds repeatable
component evidence, not a policy or paper-score reproduction. Original documents
and old negative results remain preserved; the research goal is still active.

Closing verification: the suite now passes **282 tests**, including explicit
limits on the retrospective name diagnostic. One frozen-runner style-only lint
warning remains documented; the final selected-scope configured-key scan finds
zero matches. Cycle 18A is registered, not yet implemented or executed.

## 2026-09-16 update: public-code input binding implemented and construction-audited

[Cycle 18A](043_CYCLE18A_RESULT_AND_BOUND_EFFECT_PREREGISTRATION.md) now implements
the registered revision. Corresponding literal API paths and keyword arguments
provide unique identifier mappings; needed target literal setup is retained;
ambiguous bindings, local capture and lost required outputs are rejected. The
constructor receives no task-ID, score, hidden namespace or intervention-outcome
fields. Earlier frozen operators and native worker code remain unchanged.

All 34 original candidates are accounted for: five accepted changed proposals,
eight accepted unchanged proposals, and 21 rejections. The complete registry
regenerates from frozen public inputs. Four previously passing old-task edits
remain accepted unchanged. Twenty focused construction tests pass, and the full
suite reaches 308 tests with the new effect-schema checks. The construction gate
is KEEP for a separately registered all-five effect test, which is now running
with three fresh factual controls and zero model calls. No new task repair,
contract admission, learned scope or held-out advantage is claimed by this update.

## 2026-09-16 update: second build-scenario repair independently audited

[Cycle 18B](044_CYCLE18_BOUND_REPAIR_RESULT.md) is complete. All five bound edits
and three factual controls pass replay/integrity checks; one edit on b7a9ee9_1
changes factual native failure to success with no new uncaught error positions.
The independently audited primary metric is one newly repaired task, so the
decision is KEEP the local bound-repair finding. Four other edits remain failures.
The complete run uses 16 native executions and 16 scorers, zero model calls and
zero new API USD. The passing edit increases native API-log entries by 34.

This adds a second locally repaired build scenario to the old aa8502b result.
It does not yet establish two supports for one abstract contract: neither a
shared executable verifier nor its scope has been automatically learned and
validated. The new successful-origin harmful-flip guard, static/text/equal-compute
controls, admission and group-disjoint transfer remain missing. Saved future
actions are unchanged, so this remains a local open-loop program intervention,
not a regenerated multi-agent recovery policy. No learned-method performance
advantage or submission readiness is claimed; the research goal remains active.

## 2026-09-16 update: executable syntactic proposals fail the complete context diagnostic

[Cycle 19](046_CYCLE19_PREDICATE_RESULT_AND_CONTEXT_LIMIT.md) adds a generic,
data-selected executable predicate proposal language, kept outside the main
contract runtime. Uniform AST node/field-edge counts yield 454 threshold clauses;
18 fit both repaired source pairs. None matches all 48 previously recorded native
effect/control labels. The preregistered decision is REVISE, with zero admissions.
All features, rejected clauses, predictions, overlaps and negative outcomes are
preserved and regenerate exactly after serial independent source-effect audits.

One identical-code pair has opposite native outcomes at different saved states.
Public code/error inspection finds an omitted initializer, earlier assignments
in one prefix and a missing-name error in the other. This illustrates both a
need for public context and a labeling limitation: final success is not a unique
annotation of boundary correctness. Conservative static checks may reject code
that happens to work in one state; that alone does not make them bad verifiers.

The new proposal mechanism uses no task names, API names, literal values or
hidden state, but its feature language is human-defined and its predicates are
not semantic invariants. This update therefore does not establish an induced,
validated stateful contract, learned applicability or held-out gain. Next is a
bounded shared public-observation gate at saved boundaries, followed by local
violation/scope and static/equal-compute tests. Cycle 19 makes zero model/native
calls and adds no API cost. The original two local repairs remain retained.

## 2026-09-16 update: public context is observable without privileged introspection

Cycle 20's proposed type/length envelope fails an early check against the exact
frozen action policy: namespace enumeration and type introspection are forbidden.
No native probe was executed for that full envelope, no guard was changed and
no hidden state was substituted. The failed preflight is preserved explicitly.

A separately registered [cycle-21 presence-only query](049_CYCLE21_PUBLIC_PRESENCE_RESULT.md)
then passes all three existing source checkpoints: six cells, twelve native
executions/scorers and an independent raw-process/state/score audit. Ordinary
named references export only fixed present/absent messages. The query leaves
supported state, original public outputs, native task scores and API-log counts
unchanged. It adds one public code action per probe arm and must be budgeted
equally across future methods. It is not the abandoned type/length envelope.

The known conflicting source states now publicly distinguish the presence of
the omitted collection input. Presence alone is not a correctness requirement:
a later action may initialize an absent variable. Next is a local-error labeling
and standard static-name-checker component diagnostic, separating missing-input
errors from final-task outcome. No novel memory, learned semantic contract,
admitted bank or held-out advantage is established. These cycles add no model
calls or API charges; original documents and previous negative results remain
unchanged. The full research goal remains active.

## 2026-09-16 update: standard checker control passes, learned semantics remain open

[Cycle 22](051_CYCLE22_STATIC_CONTEXT_RESULT.md) completes all 14 registered
action/checkpoint records and both unchanged Ruff F821 configurations. Public
entry-context declarations reduce false warnings from one to zero while both
configurations detect all five reported missing-name errors. The independent
auditor repeats all 28 CLI invocations exactly and regenerates the full metrics.
Decision KEEP applies only to this standard static control component.

The local target is reported uncaught NameError, not final native task success.
Four checker-clear actions still fail the task, so semantic procedural
discrimination remains unresolved. No learned contract, scope, admission,
recovery effect or held-out gain is established. Tests pass 404; cycle 22 adds
zero native/model executions and zero API USD. All prior results are preserved.

[A focused primary-literature correction](052_PROCEDURAL_GRAPHS_NOVELTY_UPDATE.md)
also narrows the novelty claim. The next experiment must test genuine
evidence-derived procedural logic beyond competent controls; contrastive edits
and validation alone cannot carry the contribution. The research goal remains
active, and the current implementation is not submission-ready.

## 2026-09-16 update: richer proposal diagnostic prepared, no generated result yet

[Cycle 23's input stage](054_CYCLE23_INPUT_PREFLIGHT_STATUS.md) is implemented and
twice regenerated. It prepares two prompt folds, contrast/success-only modes and
three paired request seeds: 12 requests, none sent. All 14 existing diagnostic
runtime records contain only normalized public code and observed present names;
string literals are redacted and labels remain separate. The two source/repair
pairs are bound to the same original contexts. Full tests pass 415.

This is preparation for testing a richer code-inspection representation after
the AST-count failure, not a new semantic contract, transfer result or learned
advantage. The isolated generated-code runtime and final generation freeze are
still pending. Source labels concern original saved continuations, not execution
of normalized code. Strong semantic controls, recovery/scope/admission and
untouched-group evaluation remain required. No new API cost has been incurred.

## 2026-09-16 strict decision: REVISE the research formulation

[The Cycle-22 decision report](056_CYCLE22_STRICT_DECISION_REPORT.md) closes the
user-requested gate with every record and explicit falsifiers. Retain the public-
context F821 component: one beneficial checker-decision flip, no harmful checker
flip, all five observed NameErrors detected. Task-level intervention flips are
unmeasured, and four checker-clear actions still lead to native task failure.

No extra privileged runtime information or attributable learned-contract gain
exists. A future rule must make a useful semantic/scope decision beyond a
competent manual procedural control under identical public inputs and common
repair branches. The report proposes one bounded held-out activation test and
explicit go/no-go thresholds; it does not execute or preregister a new cycle.

The isolated-runtime preflight completed ten fixtures with two container runs
each, but its subsequent generation-runner draft is untested, unfrozen and
unexecuted. The current known-build Cycle-23 plan is paused and all files are
preserved. The decision is not submission readiness, a learned-method win or
proof of a superior pivot. The full research goal remains unresolved.

## 2026-09-16 post-gate correction: semantic truth and inputs remain insufficient

[A bounded manual-control analysis](057_MANUAL_CONTROL_SPEC_AND_SEMANTIC_INFORMATION_LIMIT.md)
uses only the two public task instructions, relevant API documentation and saved
programs. Both repaired producers address APIs defaulting to page 0 with five
items. The native-successful b7a9ee9 repair still uses `artists[0]`, which cannot
certify the general all-artists requirement under the public list schema.
The saved native success is not changed; the issue is what it can substantiate.

The analysis also constructs an exact input collision on that actual source:
changing the requested genre comparison produces different code but the same
all-string-redacted runtime input. Two focused tests demonstrate these bounded
information limits without executing source programs or collecting new native
scores. The paused twelve-request proposal diagnostic must not proceed unchanged.

The next scientifically meaningful target would require information-preserving
public task/API inputs, a competent manual semantic control and labels tied to
specific repair effects rather than assumed universal correctness. This is a
research revision, not a demonstrated learned policy or a validated pivot. No
new model call, API cost, contract admission or infrastructure framework is added.

## 2026-09-16 post-gate implementation: manual control closes the observed F821 gap

[The implemented manual-control diagnostic](059_MANUAL_CONTROL_RESULT_AND_LEARNING_GAP.md)
uses the corrected public task/API/code/presence views on all fourteen frozen
records. Human pagination rules flag all four B-clear native failures. Together
with B, they flag all nine saved failures and no saved successes. The full manual
reference additionally checks consumer semantics and flags the passing
first-artist-only repair; its warning is retained and its native success is not
relabelled. These are post-hoc known-development associations, not causal task
flips, held-out performance or a learned contribution.

The exact genre-filter representation collision is repaired by targeted literal
credential redaction; all fourteen credential occurrences are masked while the
changed genre remains distinguishable. The old negative evidence and paused
proposal implementation remain preserved. The new view is not integrated into
that paused runtime and does not authorize resuming the old requests unchanged.

Full tests pass 464; new-code scoped lint passes. No new native, model, Ruff
experiment or sandbox execution occurs and new API cost is USD 0. REVISE remains:
the observed residual failure class is covered by manual logic, so future work
needs attributable repair-selection value beyond that control, not more
known-build predicate fitting. Such a pivot is still unvalidated.

## 2026-09-16 saved-branch analysis: manual activation reaches the local quality ceiling

[The next bounded analysis](061_SAVED_BRANCH_SELECTION_RESULT.md) pairs the eleven
edited branches in the fourteen-record sample with their exact factual controls.
Whole requests differ only at the target action and saved pre-action states
match. No-op obtains 5/11 successes; always-edit obtains 4/11 with three beneficial
and four harmful flips. A hand-coded strict warning-subset reduction policy
obtains 8/11, three beneficial and zero harmful flips, equal to the quality oracle.
Unlike an all-clear rule, it permits the beneficial partial playlist repair.

These are post-hoc offline recombinations of native outcomes, not new policy
rollouts or held-out results. There are only two known scenarios and three
checkpoints. Thirty other historical edits are inventoried but not silently
evaluated using missing public context. The selected branches add 66 native
API-log entries versus no-op; zero quality headroom does not prove an efficiency
ceiling. Full tests pass 473 and no new model/native execution or API cost occurs.

Learning to select these same supplied branches cannot improve their observed
quality over the stronger manual reference. New repair content, independent
failure contexts or a measured efficiency/authoring-effort hypothesis would be
needed; none is yet validated. REVISE remains and the old proposal run stays paused.
