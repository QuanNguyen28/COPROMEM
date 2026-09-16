# CoProCon research branch: current implementation and evidence

Date: 16 September 2026. This guide describes the research-branch additions, not
the historical proposal as if it had already been demonstrated. Original documents
in `docs/` remain unchanged. Dated cycle records and raw outputs take precedence
over this navigation guide when interpreting a specific experiment.

## What the project is testing

Can a fixed planner/solver workflow learn a small executable constraint from
matched successful and failed handoffs, then use it to improve unseen tasks beyond
the same workflow with a strong static verifier and matched retry controls?

The main object is a scoped contract, not an agent-routing policy. The team and
model are fixed within a comparison. Historical code includes a synthetic
join-cardinality experiment whose decisive verifier logic is domain-written.
It demonstrates execution/recovery behavior, not automated discovery or novelty.

The new learner is deliberately narrow: it mines field presence, nonempty values,
JSON types, and homogeneous list-element types from build artifacts. Field names
come from data. It cannot detect an incorrect arithmetic result when all fields
remain structurally valid. Invariant mining itself is established prior work.

## Current components

| Module | Responsibility | Important boundary |
|---|---|---|
| `checkpoints.py` | Frozen public planner artifact, content-addressed request/response cache, write-once storage | Gold answers are absent from checkpoints and provider prompts; identical requests share one saved draw |
| `providers.py` | Pinned OpenRouter route, metadata, seeds, pre-request budget reservations, retry accounting | Seeds do not guarantee provider determinism; ambiguous failed requests retain cost reservations |
| `paired_gsm8k.py` | Six-arm immutable-checkpoint schema diagnostic and task-cluster bootstrap | Its `copromem` arm is explicitly the historical hand-written schema; it is not genuine induction |
| `induction.py` | Same-task/context pairing, structural proposal, public categorical scope, replay admission, greedy clause deletion | Proposal reads build only; minimization reads development only; final outcomes never select clauses |
| `contract_runtime.py` | Shared verifier and recovery path for static and induced predicates | Contract origin is not injected into prompts; same executable logic produces identical effective requests |
| `induction_pilot.py` | Configured source collection, development minimization, audit, frozen candidate evaluation | An empty bank stops evaluation; this is a valid negative result, not a reason to relax gates |
| `structural_audit.py` | Offline build-only feature-signature comparison | Diagnosis only; cannot admit contracts or claim causal prediction |
| `research_pilot.py` | Historical-schema paired diagnostic runner | Train-only, bounded and logged; use the induction runner for actual learned candidates |

## End-to-end procedure

1. Save configuration, branch/base commit, source hashes, provider metadata and task selection.
2. Collect multiple planner/solver rollouts on build tasks. Preserve raw generations.
3. Pair outcomes from the exact same task, interface, public context and execution configuration.
4. Mine candidate clauses with support from at least two independent source tasks.
5. Replay and greedily minimize on disjoint development tasks.
6. Freeze each selected candidate before a separate benign-task audit.
7. Admit only candidates passing predeclared benefit, harm and data sufficiency gates.
8. Compare frozen candidates on disjoint held-out development tasks; final test remains unopened.

The present admission thresholds are pilot gates, not a statistically calibrated
safety guarantee. Eight benign audit successes, for example, would not establish
a negligible population harm rate. Public benchmark-name scope is not meaningful
semantic scope learning. There is no validated multi-contract retrieval policy in
the new real-task runner; each admitted candidate is evaluated separately.

## Fairness and interpretation

Every intervention continues from the same planner checkpoint. The no-memory,
success-only, textual-rule, sham-retry, static-verifier and induced-contract arms
share the task, model route, scorer and decoding caps. Learned/sham controls share
activation for testing feedback value. Clause deletions are included when a bank
exists. A single-clause deletion reduces to the no-intervention control.

Matched caps are not identical realized costs: activation and prompt lengths differ.
Report actual calls/tokens/USD, not just budgets. Count a logical planner share for
each arm, while charging the physically collected planner only once. Cached
identical requests create common draws, not extra independent observations.
Different prompts remain stochastic even with matching seeds. Bootstrap clusters
are tasks; multiple rollouts from one task are not independent tasks.

Moving success memory to the solver preserves the planner checkpoint, but is an
adaptation of the original planner-memory baseline. The local ExpeL/AWM/CRITIC
variants are also adaptations, not published-score reproductions.

## Evidence so far

- Cycle 1: four development tasks, two replicates; no-memory 8/8, static 7/8,
  sham 7/8. Historical CoProMem was not admitted and exactly matched no-memory.
  This is no evidence of learning. Cost: USD 0.00152572.
- Cycle 2: twelve build tasks, three rollouts; 35/36 successes, one matched task,
  zero candidates. Both available success/failure pairs have identical structural
  signatures. Cost: USD 0.00209930. Decision: REVISE.
- Cycle 3: preregistered same-task second-model sensitivity diagnostic. Consult its
  dated decision record when complete; do not infer success from a running process.

Synthetic regression reproduces the historical 81.25% contract success, equal to
the static verifier. Positive tiny synthetic results remain controlled feasibility
fixtures, not real-model or cross-benchmark evidence.

## Run and inspect

From the repository root in PowerShell:

```powershell
$env:PYTHONPATH = 'src'
python -m pytest
python -m ruff check src tests
python -m copromem.induction_pilot --config research/configs/cycle02_induction.json --env .env
python -m copromem.structural_audit --store artifacts/research/cycle02_induction
```

Existing configurations point to write-once run directories. Resuming completed
requests reuses cached responses; altered experiments need a new cycle ID and
directory. Do not edit a past preregistration to make a new run fit it. API keys
belong only in the ignored `.env`, never in source, commands, logs or reports.
The old `copromem-gsm8k-real` entrypoint now delegates to the induction runner;
legacy Python functions remain for provenance and are not the research default.

Raw outputs live under `artifacts/research/<cycle>/`: `protocol`, `provenance`,
`dataset`, `provider`, `calls`, `checkpoints`, `source_evidence`, `source_outcomes`,
`induction`, `replays`, `evaluation`, `reports`, and budget reservations/settlements.
Some directories appear only when that stage is reached. Evaluator gold labels
are saved separately from public handoffs; do not feed dataset records into a model.

## Research records

- `000_initial_state.md`: starting branch, commit, document hashes, baseline tests.
- `001_cycle_decision.md`: paired schema diagnostic and individual harmful flips.
- `002_induction_preregistration.md`: proposal language and fixed admission gates.
- `003_cycle02_decision_and_cycle03_preregistration.md`: negative source result and next test.
- `CLAIM_EVIDENCE.md`: append-only claim status, including contradictory evidence.
- `NOVELTY_MATRIX_20260916.md`: primary-source overlap and remaining hypotheses.
- `BENCHMARK_BASELINE_SHORTLIST.md`: six research baselines, four benchmark families,
  required adapter tests, and reproduction limitations.

The project is in **mechanism validation and formulation revision**, not main
experimentation or submission readiness. A useful bank, a strong static-control
comparison, meaningful learned scope, broader validated adapters, uncertainty and
cross-domain evidence are still missing.

## Later same-day update (append-only)

Cycle 3 finished with 25/36 source successes, 11 failures, five matched tasks,
zero candidates and an empty bank. All ten matched pairs were structurally
indistinguishable; six had identical full artifact content. See
`004_cycle03_decision.md` for the PIVOT decision, unit/scoring caveats and cost
reconciliation. The pivot is away from schema-only outcome attribution toward
effect-validated stateful handoff contracts, not a claim that the replacement works.

Cycle 4's offline repair-effect audit rejects both static and sham promotion:
each had zero beneficial and one harmful flip. No new API calls were used.
See `005_cycle04_offline_preregistration.md` and
`006_cycle04_decision_and_adapter_preflight.md`.

All three paid archives pass `artifact_audit.py`: 198 completed generations,
200 HTTP attempts, USD 0.00515617 in settled generation usage, and USD 0.00621667
including conservatively reserved ambiguous retries. Content hashes and budget
reservations reconcile. Hashes detect accidental corruption, not adversarial
rewriting of every record.

The miner's later v2 fix also vetoes clauses contradicted by **unpaired** successful
build examples. Offline reanalysis still produces zero candidates in cycles 2 and 3;
old proposals/reports are preserved. Transport-overrun accounting now records an
unexpected actual charge and prevents further requests, including after restart.

The literature CLI now requires explicit legacy-protocol opt-in before network
or credential access. Its local-only reconciliation path needs no API key and
refuses to overwrite an existing report. It remains an adaptation, not a fair
replacement for the new paired induction comparison.

AppWorld setup is isolated under `.research-envs/appworld-013`; package/data caches
are excluded from Git but preserved locally. Setup and adapter status are recorded
separately from method results. No published AppWorld score is claimed.

## Detailed English documentation and final preflight update

- [Current code and research evidence](009_CURRENT_CODE_RESEARCH_DOCUMENT.md):
  full architecture, historical versus new learner, algorithms, controls,
  actual results, costs, limitations and research phase.
- [Effect-validated contract research specification](008_PIVOT_RESEARCH_SPECIFICATION.md):
  the proposed next formulation and falsification/promotion gates.
- [Native adapter and resume audit](010_NATIVE_ADAPTER_AND_RESUME_AUDIT.md):
  Windows/Linux findings, our corrected clock-probe mistake, source-provenance
  protection and exact-source reproducibility limitations.

The corrected AppWorld Linux probe restores database completion but not a saved
Python variable, and native restore/cleanup fails in the clock lifecycle. Two
fresh-process authored-prefix probes match and close normally. This favors testing
fresh-process prefix replay; it does not validate a complete agent adapter.
No new model calls were used. Local verification is now 76 tests plus Ruff checks.

**Important run-command clarification:** the earlier CLI examples describe the
historical configuration. Since source code has changed, paid CLIs now refuse to
resume those old directories. Do not edit a past configuration or bypass this
guard. Inspect/reanalyze completed archives without API calls instead:

```powershell
$env:PYTHONPATH = 'src'
python -m copromem.artifact_audit --store artifacts/research/cycle01_paired --store artifacts/research/cycle02_induction --store artifacts/research/cycle03_induction --output-store artifacts/research/integrity_20260916
python -m copromem.structural_audit --store artifacts/research/cycle03_induction
```

An intentionally changed experiment needs a new preregistration, cycle ID and
output directory. New paid runs snapshot exact source text. Earlier cycles retain
hashes and raw evidence but not every intermediate uncommitted source tree.

## Cycle 5: sandbox and native scorer update

See [012_CYCLE05_SANDBOX_AND_NATIVE_SCORER.md](012_CYCLE05_SANDBOX_AND_NATIVE_SCORER.md).
Four repeated prefix fixtures now validate saved state, public observations and
separate native evaluation; native timeouts and forbidden actions are recorded.
An explicitly privileged official reference solution passes 5/5 scorer checks,
whereas a mere completion flag does not solve the task. Oracle evidence is
excluded from learning, and its scenario group is excluded from future selection.

The Docker runtime has no network/user workspace/API key, uses a non-root account,
and retains native guards. It is a bounded common-harness adaptation, not a formal
Python-sandbox proof or a finished learned-agent adapter. There are now 94 passing
local tests. This cycle used no model calls and does not change the negative
learned-contract conclusions from cycles 1–4.

Offline inspection commands:

```powershell
$env:PYTHONPATH = 'src'
python -m copromem.stateful_adapter audit --store artifacts/research/cycle05_stateful --pair empty-a empty-b --pair mutating-a mutating-b --pair unicode-a unicode-b
python -m copromem.stateful_adapter audit --store artifacts/research/cycle05_stateful --pair recovery-a recovery-b --expected-error-index 0
```

## Cycle 6: preregistered live source collection

See [013_CYCLE06_SOURCE_PREREGISTRATION.md](013_CYCLE06_SOURCE_PREREGISTRATION.md).
The typed live/replay diagnostic and independent native evaluations agree; all
110 tests pass. A fixed planner/executor no-memory pilot is registered for four
training scenarios with two replicates, excluding the entire oracle-used scenario.
Its USD 0.25 cap covers source collection, not a learned-method comparison.

```powershell
$env:PYTHONPATH = 'src'
python -m copromem.stateful_source --config research/configs/cycle06_appworld_source.json --env .env
```

As with older runs, rerun only with unchanged source provenance. A completed
archive should be audited offline; do not change its protocol to manufacture a
different result. Mid-episode interruption currently requires explicit audited
recovery rather than an implicit restart.

The subsequent [public-interface audit](014_APPWORLD_PUBLIC_INTERFACE_AUDIT.md)
documents onboarding and output-format differences from the official minimal
AppWorld agent. It did not change the frozen cycle-6 run. These differences must
be addressed as shared infrastructure, not advertised as learned memory.

Cycle 6 is now complete: [full results and critique](015_CYCLE06_SOURCE_RESULTS.md).
All eight registered episodes failed native scoring; all eight independent
prefix/scorer replays matched. The primary metric is zero mixed-outcome scenarios,
so no success/failure induction bank can be claimed. Cost: USD 0.06122978.
Decision: REVISE common onboarding/output format before memory comparisons.

```powershell
$env:PYTHONPATH = 'src'
python research/scripts/audit_stateful_source.py --store artifacts/research/cycle06_appworld_source --native-pair-audit
```

The next protocol is implemented and registered in
[016_CYCLE07_ONBOARDING_PREREGISTRATION.md](016_CYCLE07_ONBOARDING_PREREGISTRATION.md):
same model/scenarios and limits, clearer shared public onboarding, raw Python
executor output. All 119 tests pass. At registration it has not made paid calls;
it must not be described as a successful fix before its source pilot is run.

Cycle 7 is complete: [results and the next backend preregistration](017_CYCLE07_RESULTS_AND_BACKEND_PREREGISTRATION.md).
All eight native tasks still fail, despite markedly fewer syntax errors; all
eight replay/scorer pairs match. Cost USD 0.05485080. Cycle 8 keeps the common
workflow and sample fixed while testing a pinned Qwen/Nebius backend; it remains
source collection, not a memory comparison.

Cycle 8 is complete: [results and coding-backend preregistration](018_CYCLE08_RESULTS_AND_CODER_PREREGISTRATION.md).
It produced valid Python throughout but still 0/8 native successes; all eight
replay/scorer pairs match. Cost USD 0.09919890. Cycle 9 tests Qwen3-Coder through
a fixed DeepInfra route with the same workflow/sample and a USD 1 cap, still only
source collection. There is no admitted real contract bank or learned advantage.

Cycle 9 is complete: [result and next local runtime gate](020_CYCLE09_RESULTS_AND_RUNTIME_GATE.md).
The coding backend still yields 0/8 native successes (USD 0.19375710); seven
episodes are replay-eligible and one retains unsupported infinity-valued state.
That episode is not silently admitted. A zero-model-call runtime extension and
baseline resource audit precede any further paid comparison.

The same [runtime-gate record](020_CYCLE09_RESULTS_AND_RUNTIME_GATE.md) now includes
its completed zero-model-call result: 25-action live/replay and the exact formerly
unsupported prefix both match supported state and native scoring. All 143 tests
pass. This retains bounded infrastructure only, not a learned-method claim.

Cycle 11 is complete: [result and next exact-action cross-over](022_CYCLE11_RESULTS_AND_CROSSOVER_PREREGISTRATION.md).
The registered longer context/horizon yields 1/8 native success and one mixed
build scenario; all eight replays match. Cost USD 0.44051750. All public history
fits the declared context in this run. This is useful source evidence, not a
learned intervention or a causal improvement over the shorter-horizon pilot.

ExpeL now additionally passes [a real-embedding native retrieval fixture](019_EXPEL_NATIVE_REPRODUCTION_PROGRESS.md),
using a hash-verified, revision-pinned local checkpoint without network or paid
calls. Actual task rollout, insight generation and fair shared adaptation remain
unreproduced. The research objective and submission-readiness gates remain open.

The [cycle-12 cross-over result](022_CYCLE11_RESULTS_AND_CROSSOVER_PREREGISTRATION.md)
is complete: swapping saved final programs rescues the failed origin and breaks
the successful origin, with exact pre-action state/planner binding and matching
independent replays. Zero paid calls; one build task only. This establishes a
local whole-program effect, not a minimal learned contract or held-out gain.

Cycle 13 now [derives and validates a smaller producer-block repair automatically](025_CYCLE13_RESULTS_AND_RESEARCH_STATUS.md).
The generic operator extracts one block from the saved source pair and preserves
the failing program's remaining statements. It passes native scoring at both
exact checkpoints; four deletion variants are rejected after testing both
origins. All ten cells/twenty native executions replay consistently. This is
unadmitted, one-task repair evidence—not learned scope, a contract-bank win,
global minimality or novelty beyond established automated program repair.

```powershell
python research/scripts/audit_procedural_diff.py
```

ExpeL's [native ALFWorld environment gate](024_EXPEL_ALFWORLD_NATIVE_GATE.md) also
passes on a pinned, hash-selected train fixture after a scoped native-library
temporary-directory repair. The two original failures remain recorded. Neutral
actions/reward/termination reproduce twice; no model-backed or solved rollout
is claimed. The full host suite passes 197 tests. Independent source support,
transferable scope, static/equal-compute comparisons and faithful policy-level
baseline reproduction remain the next scientific gates.

The [cycle-14 independent-source extension](027_CYCLE14_RESULTS_AND_NEXT_SOURCE_DECISION.md)
is complete: four new build scenarios, eight episodes, four native successes,
seven eligible replays, **zero new mixed-outcome pairs**. Decision: REVISE source
acquisition, not promote a memory claim. The reserved partitions are unchanged;
all 98 public-bundle files and frozen collector sources pass an allocation audit.
The excluded replay has unsupported `re.Match` state, with no observed fingerprint
or score discrepancy. USD 0.925044 was settled; no unsettled requests remain.
The complete suite now passes 212 tests. An all-pair proposal screen returns zero
new proposals and reproduces the one old cycle-11 proposal as a regression check.

```powershell
python research/scripts/audit_stateful_source.py --store artifacts/research/cycle14_appworld_source --native-pair-audit
python research/scripts/screen_source_repairs.py --store artifacts/research/cycle14_appworld_source
```

The novelty audit adds omitted AutoGuide/ERL comparisons. AutoGuide enters the
six-method priority shortlist; AWM remains preserved as a reserve. A bounded,
explicitly source-only reflection-assisted retry is the next diagnostic to
register; it has not yet run and is not itself an executable-contract result.

The subsequently registered [cycle-15 reflection-assisted retry is now complete](030_CYCLE15_RESULTS_AND_SOURCE_REVISION.md):
3/8 native successes, 8/8 replay-eligible retries, **zero newly mixed scenarios**
out of seven opportunities. Decision REVISE. All 544 calls settle at USD 1.0771182;
the full suite passes 233 tests. The combined 24-episode screen retains only the
one old task/proposal; the new same-task donor supplies no additional final-action
proposal. Exact note inputs, costs, context omissions and the audit-launch race
are documented. Run materializing audits serially for a given store.

Baseline progress: [ReasoningBank official source audit and toy-embedding cache
fixtures](029_REASONINGBANK_OFFICIAL_SOURCE_AUDIT.md), explicitly not native
embedding/policy reproduction. The next source route is a separately gated
[official train-output archive inventory](032_ARCHIVE_V010_RESULT_AND_V013_INVENTORY_GATE.md).
Only filename metadata has been inspected so far; no archive task payloads have
entered induction. Neither route establishes a learned advantage or permits
reserved-test development.

The [nested archive inventory and exact next public-file gate](033_TRAIN_ARCHIVE_INVENTORY_RESULT_AND_PUBLIC_FILE_GATE.md)
identify the single official train run covering all eight existing build tasks.
Only 32 public log/version files are authorized for selective inspection next;
DB/evaluator and other-task/split bodies remain excluded. No archive trajectory
has yet been replayed or admitted as a donor.

### 2026-09-16: cycles 16 and 17A supersede the source-status notes above

[Cycle 16](037_CYCLE16_RESULTS_AND_ALIGNMENT_LIMIT.md) extracts only the 32
registered public log/version files and completes all eight local source replays.
Four sequences succeed locally; all eight pass independent replay/scoring audits.
One new build task becomes mixed. Decision KEEP the offline source route only;
the historical agent/model/prompt/cost is not reproduced. The old final-action
operator still yields zero new edits. No archive evaluator/DB bodies are used.

[Cycle 17A](039_CYCLE17A_RESULT_AND_EFFECT_PREREGISTRATION.md) expands alignment
under a separate preregistration: 1,323 action pairs, 34 candidate provenance
records, 26 distinct target-boundary/program interventions. It covers the new
task syntactically and passes full regeneration. These are unvalidated proposals.
The separately registered all-26 native saved-continuation effect test is now
running with four factual controls; no effect result or admission is claimed yet.
No model calls or new API charges occur in these diagnostics. The complete host
suite passes 278 tests. Audits that materialize records must run serially per store.

```powershell
python research/scripts/audit_official_source_replay.py
python research/scripts/screen_archived_source_repairs.py
python research/scripts/screen_all_boundaries.py --audit-only
```

The original documents remain unchanged. There is still only one validated local
repair, no learned scope or admitted stateful contract bank, and no held-out
advantage over strong static/text/equal-compute controls.

### 2026-09-16: cycle 17B completed, decision REVISE

[The full all-candidate effect result](041_CYCLE17_EFFECT_RESULT_AND_BINDING_FAILURE.md)
is now audited: four factual controls and 26 interventions, all replay-eligible,
60 native executions/scorers, zero model calls/API USD. Four edits pass only on
the old task; none of the six new-task edits succeeds. Four checkpoints in one
episode do not supply four independent task supports. Every passing edit adds
16 native API-log entries; no efficiency advantage is claimed.

The exhaustive diagnosis identifies missing donor-input names in fourteen edited
actions. [Cycle 18A](042_CYCLE18_PUBLIC_BINDING_PREREGISTRATION.md) registers a
generic public-code binding/output-closure revision; it has not yet been implemented
or tested on the corpus. The stateful bank remains unadmitted, with no learned
scope or held-out method gain. The full host suite passes 280 tests.

[AgentSpec's pinned parser/source-body fixtures](040_AGENTSPEC_PINNED_PARSER_AND_ENFORCEMENT_AUDIT.md)
also repeat, with framework/bootstrap limitations and adaptation issues explicit.
Original research documents, historical evidence and upstream baseline files
remain preserved. The research objective remains active.

### 2026-09-16: public-code binding construction complete

[Cycle 18A](043_CYCLE18A_RESULT_AND_BOUND_EFFECT_PREREGISTRATION.md) applies a
new generic binding/closure constructor to every original proposal. It sees only
public code, not task IDs, native scores or hidden state. Five changed candidates
remain; eight are unchanged and 21 are rejected. All records regenerate, and all
four old passing edits remain accepted unchanged. Twenty focused construction
fixtures pass; the complete suite now passes 308 tests after adding effect-schema
checks. Earlier frozen implementations remain intact.

The separately preregistered five-effect/three-control native experiment is
running with zero model calls. Construction acceptance is not yet evidence of
native success, learned scope, admission or held-out gain.

### 2026-09-16: cycle 18B completed, local-repair finding retained

[The complete bound-input effect result](044_CYCLE18_BOUND_REPAIR_RESULT.md)
has one passing edit among all five registered interventions, with three fresh
factual controls. The independent audit verifies all 16 native executions and
scorers. This is the first automatically derived local repair on a second build
scenario; it adds 34 native API-log entries. Decision KEEP this bounded repair
finding, not contract admission, equal-compute superiority or held-out gain.
The other four interventions remain failures. No new model calls or API charges
occurred; 308 tests pass. Two repaired procedures are not yet two supports for
an automatically inferred, scoped executable contract.

### 2026-09-16: cycle 19 rejects a code-only predicate proposal

[The complete predicate diagnostic](046_CYCLE19_PREDICATE_RESULT_AND_CONTEXT_LIMIT.md)
enumerates 454 generic AST-count clauses. Eighteen fit the two rescued training
pairs, but zero agree with all 48 existing effect/control labels. Decision REVISE.
An identical edited program has opposite native outcomes at two source states;
public source/error evidence identifies a missing collection input in one case.
No hidden state enters the miner, and no predicate is admitted. This is a known-
build representation/label diagnostic, not a held-out method comparison. The
next gate is a shared public, read-only boundary-context interface. No new model
calls, native executions or API charges occur in cycle 19.

Closing checks: **345 tests pass**, original documents/HEAD remain unchanged,
and the selected-scope configured-key scan finds no matches. One old frozen
runner's style warning remains disclosed. [Cycle 20's public-observation gate](047_CYCLE20_PUBLIC_BOUNDARY_OBSERVATION_GATE.md)
is registered but not implemented or run. The research goal remains active.

### 2026-09-16: full-envelope preflight rejected; public presence gate passed

The [cycle-20 preflight](048_CYCLE20_PREFLIGHT_RESULT_AND_PRESENCE_REVISION.md)
finds the frozen public-language restrictions block the proposed namespace/type
introspection. No native full-envelope cells run, and no guard is bypassed.
The separately registered [cycle-21 presence-only experiment](049_CYCLE21_PUBLIC_PRESENCE_RESULT.md)
passes all three checkpoints and all six cells, with twelve native executions
and scorers. The independent audit verifies unchanged supported state, original
outputs, scores and API-log counts. It exposes only name-presence booleans.

KEEP this limited common observation interface, not a learned-contract advantage.
[Cycle 22](050_CYCLE22_LOCAL_ERROR_AND_STATIC_CONTEXT_PROTOCOL.md) next separates
local missing-name errors from final outcomes and tests a standard static checker
with the same public context. It is registered, not yet run. No paid/model calls
were added; original documents and all earlier failures remain preserved.

Closing verification: **372 tests pass**, with only the preserved frozen-runner
style warning; the dated selected-scope configured-key scan reports zero matches.
The next checker diagnostic is registered but not executed. Research remains
active, with no admitted stateful contract bank or learned-method advantage.

### 2026-09-16: cycle 22 completes the standard missing-name control

[All 14 local-error records and 28 configurations](051_CYCLE22_STATIC_CONTEXT_RESULT.md)
are complete and exactly repeated. Both standard Ruff configurations detect all
five reported NameErrors; public context reduces false warnings from one to
zero. KEEP the context-aware control component, not a learned-memory claim.
Four checker-clear actions still fail the native task. Full tests pass 404;
no new native/model execution or API cost occurs. The next target is procedural
discrimination beyond name checking, with strong semantic and success-only
controls before admission or transfer.

[The focused novelty correction](052_PROCEDURAL_GRAPHS_NOVELTY_UPDATE.md) adds
Procedural Graphs and narrows the proposed distinction. Contrast plus downstream
validation alone is not a defensible novelty claim. Original documents, frozen
experiments and previous negative findings remain preserved; research is active.

### 2026-09-16: cycle 23 registered; public-input stage completed

[Cycle 23](053_CYCLE23_MONITOR_PROPOSAL_PROTOCOL.md) tests a richer model-proposed
code-inspection representation against success-only induction. Its
[input preflight](054_CYCLE23_INPUT_PREFLIGHT_STATUS.md) prepares 12 requests and
14 runtime records, with exact source-context binding, string-literal redaction
and no hidden/outcome fields in runtime inputs. Two invocations regenerate the
same evidence; 415 tests pass. No generated monitor or new paid/native call
exists yet. The next stage is the isolated runtime and complete pre-generation
freeze; primary construction results and all efficacy/admission claims remain
pending. Original documents and frozen experiment sources remain unchanged.

### 2026-09-16: strict Cycle-22 decision supersedes the next-cycle plan

[Decision: REVISE, not GO](056_CYCLE22_STRICT_DECISION_REPORT.md). Both standard
checker configurations detect all five observed NameErrors; context removes
one false warning. Four checker-clear records still fail the native task.
The report includes all fourteen records, aggregate counts, checker-versus-task
flip distinctions, leakage/cost checks and a bounded causal falsification design.

No learned-contract advantage is established. The isolated-runtime preflight
has passed, but current Cycle-23 preparation is paused and preserved; its draft
generation runner has not run, been tested or been frozen. Further work must
address a concrete semantic decision beyond a competent manual control, not
expand audits or count known-build fitting as efficacy. No new model calls.

### 2026-09-16: bounded manual-control check finds two semantic limitations

[The post-gate specification and counterexamples](057_MANUAL_CONTROL_SPEC_AND_SEMANTIC_INFORMATION_LIMIT.md)
identify the documented first-page/default-five-item pitfall common to both
repairs. The passing playlist repair still selects only the first artist of a
song, so saved native success is not a universal procedural certificate.
An exact mutation of its genre filter also yields an identical frozen normalized
input: the all-string redactor erases a semantically decisive distinction.

Two constructed counterexample tests pass; no target program, native episode or
model request is executed. REVISE the target/input specification; do not send the
paused twelve requests. The manual semantic specification is documented but not
misrepresented as a validated checker. Existing implementation/evidence remain
preserved, and learned repair-benefit value remains an unproven research target.

### 2026-09-16: implemented manual control covers all four observed static misses

[The fourteen-record manual diagnostic](059_MANUAL_CONTROL_RESULT_AND_LEARNING_GAP.md)
adds explicit public-task/API pagination checks to saved checker B decisions.
It flags all four B-clear native failures. Adding the consumer check also warns
on one saved success (first-artist selection); no native label is changed and no
task-level intervention benefit is measured. Human rules were developed on known
records, so this is a post-hoc control diagnostic, not held-out or learned efficacy.

The corrected shared views preserve genre semantics and redact all fourteen
credential occurrences. Full tests pass 464; no new model/native/sandbox/Ruff
experiment runs and no API cost. REVISE remains; the old proposal run stays
paused. A learning-value test must identify a decision beyond this manual logic.

### 2026-09-16: saved-branch selection reaches a manual quality ceiling

[All eleven available factual/edit pairs](061_SAVED_BRANCH_SELECTION_RESULT.md)
verify exact one-action replacement and shared pre-action state. A hand-coded
risk-reduction selector gets 8/11 successes, three beneficial and zero harmful
flips, matching the quality oracle; always-edit causes four harmful flips.
These are correlated, post-hoc development recombinations, not learned efficacy.
The rule permits partial repair instead of requiring every warning to disappear.

No quality headroom remains for learning to select those same branches. The
chosen branches add 66 native API-log entries versus no-op, so no efficiency win
is inferred. Thirty other historical edits are inventoried but not claimed
evaluated. Full tests pass 473; no new model/native calls or API expenditure.
REVISE remains; new evidence is required before a learned-value experiment.
