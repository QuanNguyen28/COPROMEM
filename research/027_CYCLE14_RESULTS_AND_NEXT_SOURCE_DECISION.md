# Cycle 14: more source successes, no new outcome contrasts

Recorded 2026-09-16 after the complete registered run and independent audits.
Decision: **REVISE** the source-acquisition design. The preregistered primary
metric is zero: no new scenario contains a usable success/failure pair. Four
successful episodes do not substitute for that criterion. The broader research
goal remains active; no learned-contract advantage or admission is established.

## Implementation and allocation

The previous goal cycle made concrete progress, not merely a status update.
This cycle adds a versioned identifier-only source extension to
`stateful_source.py`. It verifies the old protocol/allocation digests, train
manifest and regenerated historical partition. Every previously allocated
scenario remains excluded from the new build pool, including all variants.
Reserved dev/audit/evaluation groups and the oracle exclusion are unchanged.
`--prepare-only` freezes the config, collector source and preregistration before
exporting new task instructions or making provider requests.

Four new build groups were selected in the original hash order:
`ce359b5_1`, `cf6abd2_1`, `287e338_1`, `3c13f5a_1`. No task was substituted or
moved from a reserved group. These are source/build observations, not an unseen
evaluation of the old repair. The decision to collect additional source data
was motivated by cycle 13's one-task bottleneck and is disclosed as adaptive
research planning.

The model/provider, fixed two-role workflow, prompts, seeds, tools, context,
horizon, token caps and native runtime match cycle 11. The run used its frozen
collector sources throughout. Twelve selection tests check disjointness,
reproducibility, tampered registries/manifests and attempted partition changes.

## Complete outcomes

| New build task | Replicate 0 | Replicate 1 | Usable outcome contrast |
|---|---|---|---|
| Remove pre-2021 songs from Spotify library/playlists (`ce359b5`) | Fail, 5/8 checks, 40 steps | Fail, 3/8 checks, 19 steps | No |
| Mark a named bucket-list note item done (`cf6abd2`) | Success, 8/8 checks, 18 steps | Success, 8/8 checks, 11 steps | No |
| Name the most-recommended Spotify artist (`287e338`) | Success, 2/2 checks, 12 steps | Success, 2/2 checks, 17 steps | No |
| Request roommates' electricity-bill shares (`3c13f5a`) | Fail, 1/6 checks, 50 steps | Fail, 1/6 checks, 50 steps; unsupported state | No |

Native success is **4/8**; eligible source episodes **7/8**; mixed-outcome
scenarios **0/4**. All eight planned episodes were collected, with no provider
failure or outcome-dependent stopping. Six episodes marked completion, but two
of those still failed native scoring. Both electricity-bill episodes exhausted
the horizon. Check fractions describe each task's own tests; do not average
these fractions into a substitute primary metric.

There were 217 actions, 45 uncaught action errors, no Python syntax errors,
no plan/code parser fallbacks, and all 434 model responses ended with `stop`.
The two-success/two-failure scenario pattern supports heterogeneity in the
fixed team's task competence, not evidence that contrast-derived memory works.
It is not a causal improvement over cycle 11 because the tasks changed.

## Replay exclusion and context diagnostics

Seven native live/fresh-prefix replay pairs pass the bounded checkpoint and
separate native-score audits. The eighth, `c14-3c13f5a_1-r1`, retains a
`total_amount_match` value of unsupported Python type `Match`. Both executions
complete as processes, have identical saved fingerprints, and score 1/6; the
validator nevertheless rejects unsupported namespace state. This is an
unverified checkpoint, not demonstrated nondeterminism. Its failure and cost
remain in the overall denominator, and it is excluded from induction. No
historical label is upgraded and no validator is weakened to recover it.

The context audit finds 39/217 boundaries omitting earlier history under the
64,000-character cap. No visible entry exceeds its 16,000-character output or
6,000-character program cap. Seventeen outputs exceed the old 4,000-character
threshold. There are 21 exact consecutive program repeats and 13 exact output
repeats. These are descriptive diagnostics, not proof of an error's cause.
Resource pressure remains a plausible alternative explanation for hard tasks;
another global context increase is not automatically justified.

## Acquisition cost and proposal coverage

434 completed calls / 434 HTTP attempts; no unsettled attempts. Usage is
4,134,270 input plus 34,043 output tokens, 4,168,313 total, and
**USD 0.925044** settled/charged, below the USD 4 cap. Recorded provider latency
sums to 836.162 seconds; this is not end-to-end wall time and excludes local
native replay/scoring work. Through this cycle, the recorded paid pilots total
1,920 completed calls / 1,922 attempts, USD 1.77975425 settled and
USD 1.78081475 charged/reserved. The difference remains two ambiguous cycle-3
attempts; local CPU and baseline data downloads are not priced in those totals.

`screen_source_repairs.py` systematically enumerates all audited build-task
outcome pairs and applies the unchanged cycle-13 operator to completed final
actions. It retains no-pair, unfinished, unsupported-syntax and no-proposal cases.
Three additional tests exercise these distinctions and reject incomplete or
unbound audits. The full suite passes **212 tests** with clean Ruff checks.

The new corpus yields **zero pairs, zero proposals and zero admitted contracts**.
No native edited-program experiment is warranted by this screen. A regression
screen of the old cycle-11 corpus reproduces its exact audit and sole old
`liked_songs` proposal AST, while retaining the other three no-contrast tasks.
The screen is restricted to final-action alignment; zero coverage is not a
claim that no earlier action could ever be repaired.

## Evidence addresses and integrity

Store: `artifacts/research/cycle14_appworld_source`.

- Protocol: `89fb2e1bb70be45d67fe980385296b8d63a26ccaee1b4ac2d2dc97a6e8e247a1`.
- Frozen source snapshot: `9dd2c35e6e33b4139462b40b41129a31651a3105c4ce9349ab5e92c94d25e083`.
- Source report: `f1fc22ec501697738db1158de6628282e281c356cf7d1616ee901890f618baaa`.
- Independent source audit: `0ca2f7651af62e9fa84d452f4920d37f4a1d6902f0940c2e431f6d1706f10bae`.
- Proposal screen: `b8ba5f388ca61c427d18a7b916644065e2ae4432f2c3000478257193f1ba5979`.
- Context audit: `0b327ce358be3e2ae6393329872534e7778b986d3c7b8f80d3b3fd0aba06f4c9`.
- Allocation/bundle/source audit: `3d4e1f42332f6d8c798e4e119bef83b5b860d8216cd8b491c9aed43cc5bd713e`.

The allocation audit regenerates the original registry and verifies all 98
exported public files, the exact four-task directory inventory, no exported
ground truth, and unchanged frozen collector/preregistration texts. This is a
bounded integrity check, not a proof against arbitrary leakage. All raw records,
including unsuccessful and excluded episodes, remain preserved. Original MD
and DOCX hashes and branch/HEAD are unchanged; no commits or pushes.

## Hostile-review conclusion and next action

The previous local repair remains supported on exactly one task. More successful
episodes have **not** produced independent support for that repair or an admitted
scope. Do not call an empty new bank conservative success, relabel partial
test passes as successful trajectories, or tune on reserved tasks to force pairs.

The literature audit also found an omitted direct comparator, AutoGuide; the
updated novelty matrix and six-method priority shortlist explicitly correct
that omission. Conditional textual contrast memory is not an available novelty
claim. AWM's preserved reproduction work moves to reserve; it is not rejected
on performance. ERL is another relevant acquisition-efficiency alternative.

Next, revise source acquisition rather than silently increasing repetitions
until a pair appears. A concrete next diagnostic is a **predeclared, bounded
reflection-assisted source retry**, using only previous public build traces
and binary task outcomes, with no hidden test details. Keep it explicitly
separate from final method efficacy: source feedback is not a learned executable
contract, all future comparison arms must share the resulting source evidence,
and textual reflection itself must remain a strong control. Freeze the eligible
task/replicate rule, model, information and cost budget before retries; retain
all failures. This is a next experiment, not yet an implemented or run result.

The unsupported `Match` state is a separate runtime limitation. Validate any
future representation change independently and retain old exclusion labels.
Neither repairing that serialization gap nor repeating the single successful
transplant can substitute for scope, static/equal-compute controls or transfer.

## Final safety check

At 2026-09-16 05:55 UTC, the configured-key exact-byte scan finished across
29,448 files / 1,911,334,693 bytes with zero matches and zero unreadable files.
Scope: source, tests, research, artifacts, docs, vendor excluding `.git`, and root
files excluding `.env`. This is not a general secret detector or a scan of the
excluded credential file. The key value was never printed or persisted.
Append-only record:
`artifacts/research/safety_audits/d8f8f47a577d4db3fd97fa5dcf51d64b32087d5d34b2fe5feeb7ed8da37740b5.json`.
The 212-test suite, Ruff lint and four changed Python files' formatting checks
passed again. ExpeL's vendor tree remains clean; no research containers or paid
collection jobs remain active at this handoff.
