# Cycle 15: reflection-assisted source retry did not add contrast support

Completed and audited 2026-09-16 on branch `codex/copromem-research-loop`, unchanged
HEAD `18025102c010e85f26b0b3fb1144a1cb684b587e`. The research goal remains open.
The [frozen preregistration](028_CYCLE15_REFLECTION_SOURCE_PREREGISTRATION.md)
is unchanged. **Decision: REVISE** this source-acquisition protocol. Its primary
metric is zero, despite three native successes. Do not present this as a learned
contract result, a causal reflection comparison or evidence of impossibility.

## Implementation and fixed information boundary

Each of the eight previously allocated build tasks received exactly one critic
call on its original replicate 0 public history and binary native outcome,
followed by exactly one fresh retry (replicate index 2). Notes were not selected,
rewritten or corrected. `reflection_source.py` binds the raw note to its source
trajectory, exact provider request/response and task; both fixed roles receive
it inside the same 64,000-character context cap. This is declared build-only
feedback, not hidden evaluator access during evaluation or a verified contract.

The model/provider, role prompts, native image, environment seed, 50-action
horizon and planner/executor token caps were unchanged. The retry context version
explicitly adds the fallible note; therefore this is not an otherwise identical
prompt or a randomized reflection-effect experiment. All eventual method and
baseline arms must share this collection data and its cost.

Tests exercise feedback allowlisting, note/source/call binding, exact raw-note
reuse, task mismatch rejection, context accounting and old-version behavior.
Independent audits regenerate both prior corpora, all eight notes and all new
boundaries. Four further tests cover the combined old/new all-pair screen.
The complete suite passes **233 tests**, with clean Ruff lint.

## All registered task outcomes

`F/T` denote binary native failure/success. Partial native checks below are
diagnostic metadata, never information supplied to the critic or retry agents.

| Build task | Prior outcomes r0/r1 | Retry r2 | Actions | Completion flag | Native checks passed | Replay eligible |
|---|---|---|---:|---|---:|---|
| 27e1026_1 | F / F | F | 50 | No | 1/2 | Yes |
| b7a9ee9_1 | F / F | F | 11 | Yes | 2/4 | Yes |
| 60d0b5b_1 | F / F | F | 50 | No | 0/7 | Yes |
| aa8502b_1 | F / T | T | 33 | Yes | 4/4 | Yes |
| ce359b5_1 | F / F | F | 50 | No | 2/8 | Yes |
| cf6abd2_1 | T / T | T | 15 | Yes | 8/8 | Yes |
| 287e338_1 | T / T | T | 9 | Yes | 2/2 | Yes |
| 3c13f5a_1 | F / F* | F | 50 | No | 1/6 | Yes |

*The prior 3c13f5a replicate 1 retains its cycle-14 unsupported-`Match`
exclusion; its binary failure does not make it eligible for induction. This
cycle's new replay is independently supported, without changing that old label.*

Primary result: **0 newly mixed scenarios / 7 previously unmixed opportunities**,
across the complete eight-task sample. Native success is 3/8; eligibility is 8/8.
Four episodes exhaust the horizon; one of four completion flags is a false
positive. The only bad-to-good change versus the critic's fixed source replicate
is aa8502b, which already had a successful original replicate. It cannot count as
new independent support. There are no good-to-bad changes against that fixed
replicate. These are descriptive changes, **not causal beneficial/harmful flips**.

No population-level superiority test is appropriate: the primary count is zero,
tasks are a repeatedly inspected build slice, and there is no concurrent matched
no-reflection retry arm. Decoder variation, the extra attempt, note content and
changed history visibility remain competing explanations for any outcome change.

## Failure and context diagnostics

268 actions, 39 uncaught local action errors, zero Python syntax errors and zero
plan/code parse fallbacks. All 544 provider generations finish with `stop`; there
are no provider failures, HTTP retries or unsettled reservations. All notes fit
the 4,000-character note cap and are preserved as generated, not gold diagnoses.

The critic input omits 22 older history entries for ce359b5 and 6 for 3c13f5a;
the other six critic histories fit. During retries, 29/268 boundaries omit older
history: 8 for ce359b5 and 21 for 3c13f5a. No visible entry exceeds its declared
program/output cap. There are 84 exact consecutive program repeats and 85 output
repeats; repetition is descriptive and not automatically an error label. Notably,
the 27e1026 and 60d0b5b horizon failures occur without context-history omission.
Another blanket context increase is not justified by omission alone.

The generated reflections did not solve the source-policy competence problem on
this sample. This does not isolate whether the critic, fixed role decomposition,
backend, effective prompt or repeated-action behavior is decisive. Do not hardcode
task-specific fixes into the learned mechanism or simply add retries until a
favorable pair appears.

## Combined source-pair and proposal screen

`screen_reflection_repairs.py` joins all original and new episodes through their
independently regenerated audit bindings: **24 episodes across eight tasks**,
including the one old ineligible episode. It retains every eligible same-task
success/failure pair and all no-pair tasks, without choosing favorable donors.

There are exactly two outcome pairs, both on aa8502b. The original pair reproduces
the known one producer-block proposal. The new pair, original failure versus
reflection-assisted success, yields **no proposal** under the unchanged restricted
final-action operator. Total proposal count remains one, supported on one task.
No new edited-program experiment, executable verifier, learned scope, admission
or transfer follows. A final-action screen does not exhaust earlier-handoff
alignment, and repeated successes on one task are not independent scope support.

## Costs

| Component | Completed calls | Input tokens | Output tokens | USD |
|---|---:|---:|---:|---:|
| Critic reflections | 8 | 100,848 | 1,512 | 0.0317664 |
| Planner/executor retries | 536 | 4,962,900 | 28,309 | 1.0453518 |
| Total | 544 | 5,063,748 | 29,821 | **1.0771182** |

Total tokens: 5,093,569. All 544 HTTP attempts settle; charged and settled USD are
equal, below the USD 4 cycle cap. Recorded provider latency sums to 1,432.022
seconds (56.187 critic + 1,375.835 retry); this is not end-to-end wall time.
Native execution, replay, audit and download/CPU resources are not priced here.

Through cycle 15, paid experiments total **2,464 completed calls / 2,466 attempts**,
USD **2.85687245 settled / 2.85793295 charged-reserved**. The difference is still
the two ambiguous cycle-3 attempts, not a new unreported cost.

## Evidence and integrity

Store: `artifacts/research/cycle15_reflection_source`.

- Protocol: `36b0fa4baea8f37231aefa60f1fe5dd24dd2c2b1ad90593daa290f0eb1f021a0`.
- Frozen source snapshot: `57a22baf84470a74de81ef6754db6acf14419a48d2cdccb719f09cd081181f39`.
- Completed report: `4474282a6c1e8574010c95dd3afd31e285403b14dda48e225026d5511bf45557`.
- Native/source audit: `6372c78efcef4aedf7a8b3b122538e59e9fc30241c8b76f539d75e402efe9555`.
- Reflection/primary/cost audit: `4bc8f45e9fc021448005eb9ba259a5b09eaf3e7ff3173e74d7a81f8cebc5c90b`.
- Combined proposal screen: `2401d0b7b5e879570c4974aa638eb94732dec0e4849b7d4e1e31dce5835b4b48`.
- Context audit: `e24a7e189bd011cb1dc52de4dff0ad754ddfbbeb4a2d5aebb9f81600e92a7f8a`.
- Allocation/bundle/source audit: `83e11b4a2150bf5a5fe7633e0d5908e253ce3214f48211aaa5e7b9db05f1e076`.

The allocation audit regenerates both original selections, confirms reserved
partitions are unchanged, hashes all 150 exported public-bundle files and verifies
the collector/preregistration texts still equal the frozen snapshot. Original
MD and DOCX hashes, branch and HEAD remain unchanged. No commits or pushes.

One audit launch failed because two concurrent audit commands tried to create
the same derived prefix-audit file. `RunStore` has exclusive write-once creation,
not a concurrent get-or-create transaction. Both processes ended; a standalone
serial rerun succeeded and regenerated the same reflection audit as the completed
screen. No source output or score was changed, overwritten or deleted. Incident
`audit_incidents/962b4db9fc49d99bf491bc01132187a96f5244b2d25a52dfa06e065a520ba326.json`
records the limitation. **Run artifact-materializing audits sequentially per
store**; this concurrency issue must not be concealed as flawless execution.

```powershell
$env:PYTHONPATH = 'src'
python research/scripts/audit_reflection_source.py
python research/scripts/audit_context_visibility.py --store artifacts/research/cycle15_reflection_source
python research/scripts/screen_reflection_repairs.py
```

## Hostile review and next source decision

The source-support gate still fails. Do not lower the independent-task admission
threshold, call textual reflection an executable contract, count partial checks
as successful trajectories or promote the old local edit into a transferable bank.
Strong static, textual and equal-compute controls are still required for any
future learned effect. Current novelty remains heavily overlapped with existing
context-aware memory and traditional program repair.

Rather than immediately buying another set of retries, examine a different,
bounded source route: archived **official non-oracle training agent trajectories**
shared by all methods. [The metadata-only gate](031_OFFICIAL_TRAIN_ARCHIVE_INVENTORY_GATE.md)
and [version follow-up](032_ARCHIVE_V010_RESULT_AND_V013_INVENTORY_GATE.md) preserve
the initial test-only archive mismatch. A newer release has train-labelled entries
for all eight current build tasks, but no trajectory, DB or evaluator payload has
yet been opened. Exact source policy, demonstrations, native data/version, parser
and replay eligibility remain unverified. Freeze a public-file extraction and
replay protocol before using anything as a donor. No external success labels or
held-out/test outputs may substitute for native replay evidence.

Separately, [ReasoningBank's official source and ten cache fixtures](029_REASONINGBANK_OFFICIAL_SOURCE_AUDIT.md)
advance baseline provenance and adaptation checks, not native model/policy or
published-score reproduction. The research loop continues; submission readiness
and a defensible learned advantage remain unestablished.

## End-of-cycle preservation and configured-key scan

At 2026-09-16 06:42 UTC, an exact configured-key byte scan completed over source,
tests, research, original docs, root files except `.env`, all cycle-15 evidence,
the ReasoningBank source/probes and both new official-archive stores. It scanned
3,685 files / 462,442,096 bytes with zero matches and zero unreadable files.
This is an explicit selected-scope scan, not a fresh scan of every old artifact,
encoded credentials or a general secret detector; the prior full scan remains
separate. The key itself was not printed or saved in the audit.

Record: `artifacts/research/safety_audits/records/7ada9698a4fccc383a0a0f964bff2b26a347942d57cadd4ef45a7378c4b2cbc7.json`.
All 233 tests and Ruff checks pass again. No paid collection or research container
remains live. [The exact next public-file gate](033_TRAIN_ARCHIVE_INVENTORY_RESULT_AND_PUBLIC_FILE_GATE.md)
is frozen before any archived trajectory payload is opened.
