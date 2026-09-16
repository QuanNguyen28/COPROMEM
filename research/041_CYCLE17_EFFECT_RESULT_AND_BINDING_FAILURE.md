# Cycle 17B result: wider alignment does not yet yield an independent repair

Recorded 2026-09-16 after all registered cells finished and the independent audit
passed. Branch `codex/copromem-research-loop`; original HEAD remains
`18025102c010e85f26b0b3fb1144a1cb684b587e`. No user document, evaluator, source
episode or upstream baseline was changed. The [039 preregistration](039_CYCLE17A_RESULT_AND_EFFECT_PREREGISTRATION.md)
and all failed/null results remain intact.

## Completed primary result and decision

All four factual controls reproduce their original full supported state, public
outputs, completion and native score. All 26 distinct registered interventions
were executed, each followed by its unchanged saved future actions and one fresh
full-prefix replay. All 26 are replay-eligible. There are **four passing edits,
all on the old aa8502b task; zero newly repaired task IDs**.

**REVISE**, as preregistered. The new b7a9ee9 task contributes six interventions
and no success. Source availability and syntactic candidate coverage were useful
intermediate gates, but neither established a usable independent repair.

| Source origin | Distinct interventions | Passing interventions | Independent new repaired tasks |
|---|---:|---:|---:|
| c11-aa8502b_1-r0 | 20 | 4 | 0: already known task |
| c11-b7a9ee9_1-r0 | 3 | 0 | 0 |
| c11-b7a9ee9_1-r1 | 1 | 0 | 0 |
| c15-b7a9ee9_1-r2 | 2 | 0 | 0 |

The four successful cells are edits 02, 07, 12 and 15, at old-task action indices
10, 11, 12 and 13. They remain four checkpoints within one already inspected
episode/task, not four independent learning examples. Each incurs **16 additional
native API-log entries** relative to the factual full sequence. This is not an
efficiency result or an equal-tool-compute comparison.

## Exact evidence and integrity

The independent audit regenerates the complete candidate deduplication/selection,
all action substitutions and unchanged continuations, source planner/public-
handoff/state identities, raw worker/scorer outputs, native DB hashes, tool-log
counts, error positions, effect labels, complete denominator and REVISE decision.
It verifies 60 native executions, 60 separate native scorers, 139 live frames
and 79 live post-checkpoint action inputs. Frozen source text still equals the
working source at this dated audit. All model/API counters are zero; there are
no unaccounted intervention cells or infrastructure-failure replacements.

Root: `artifacts/research/cycle17_boundary_effects`.

- Protocol: `89cc48678acdb0dcb1b7d46893c4f676e905d386c0651645bb37cc7c3cfb598d`.
- Frozen sources: `751abcddb7a0671851a227213c941fbeea19cffeaa507394a969a4fda9f0785d`.
- Report: `34d849a67422629d7c6c6b35761794ed44c21765928d61fa1ff9856de415264c`.
- Independent audit: `c8423053a9a5a3ceb8bbc87a84ee6c19f7768925bde329c13899f4d223c28963`.
- Binding diagnosis: `21f5bf54dc93b53ad22f56261eca456f9e661c68ad57d0b65a2d0b8050441169`.

```powershell
$env:PYTHONPATH='src'
python research/scripts/audit_boundary_effects.py
python research/scripts/diagnose_boundary_bindings.py
python -m pytest -q
```

Run materializing audits serially per store. The complete host suite passes 280
tests. The frozen effect runner retains one style-only Ruff FURB192 diagnostic
(`sorted(ids)[0]` rather than `min(ids)`); it was not edited mid-experiment to
change its frozen identity. Other newly added audit/fixture/diagnostic files pass
their scoped lint checks. Do not describe the entire frozen runner as lint-clean.

## Failure diagnosis, not a post-hoc change to the gate

A separate exhaustive diagnostic finds missing-variable `NameError`s in 14 of
26 edited actions: eight old-task edits refer to absent `login_result`; all six
new-task edits refer to absent `spotify_access_token`. The latter name comes from
the donor's earlier setup, whereas the target programs use a differently named
input. One candidate also removes an `all_playlists` binding consumed later;
the earlier missing-token error occurs before that second possible failure.

This diagnosis uses saved public error strings and, explicitly, harness **name
availability** for retrospective inspection. It is not an agent-visible learned
verifier, a sound definite-assignment analysis, or evidence that mapping the names
will solve the task. No values from the hidden namespace were put into a prompt,
substituted into a repair, or used to revise an observed outcome. The original
26 interventions remain unchanged.

The immediate proposal defect is now concrete: the name-based block operator
does not close donor input dependencies or preserve all required target outputs.
The smallest next test is a separate generic public-code binding/closure operator,
not another paid source retry. Any proposed mapping must be inferred from shared
public API-call argument structure and must preserve target setup/consumer code;
unknown or conflicting mappings must be rejected rather than hand-coded.

## Hostile-review conclusion and remaining gates

The old local procedure can affect several boundaries in one saved episode, but
no independently repaired task has been established. Four successes among a
development search's 26 correlated candidates do not support a general efficacy
estimate. All original target episodes failed, so this experiment cannot estimate
harmful flips on initially successful episodes. Saved future programs may also
be stale after intervention; this is an open-loop local-effect estimand, not a
regenerated multi-agent recovery policy.

There is still **one unadmitted local repair**, no learned executable verifier or
validated generalized scope, no admitted stateful bank and no held-out advantage
over strong static/text/equal-compute controls. Input binding is an engineering
prerequisite, not a novelty claim. Independent support for the same abstract rule,
successful-origin guards and group-disjoint transfer remain mandatory. Source
demonstration/model/historical-cost differences remain disclosed.

The [AgentSpec component audit](040_AGENTSPEC_PINNED_PARSER_AND_ENFORCEMENT_AUDIT.md)
adds baseline implementation evidence without claiming end-to-end reproduction.
The latest exact configured-key scan at this point covers 4,654 selected files /
227,823,138 bytes with zero matches and zero unreadable files, audit
`f1a3c35f5d22127748c4535854a62874685c7eabbafb7b977544753f75a36a79`.
This dated scan excludes `.env`, Git internals and unlisted old evidence; it is
not a claim to have detected every possible encoded or unrelated secret.

Next: [cycle 18A public-code input binding and output closure](042_CYCLE18_PUBLIC_BINDING_PREREGISTRATION.md).
The autonomous research goal remains active; no scientific win or readiness gate
has been declared complete.

### Closing verification update

Two added diagnosis fixtures bring the complete suite to **282 passing tests**.
They explicitly demonstrate both missing-name detection and its lack of a sound
definite-assignment guarantee. A full scoped lint run over `src`, `tests`,
`research/scripts` and `research/fixtures` reports only the frozen FURB192 style
warning described above. No native experiment containers remain running.

The subsequent selected-scope key scan covers 4,661 files / 227,868,364 bytes,
with zero matches and zero unreadable files:
`6120ddf4d559b8281d8bb156d1386a152fa6f01aa2a86662315a0dbbb339f7d8`.
Both original document hashes, branch and HEAD are reverified unchanged. Cycle
18A is registered but has not yet been implemented or run; no user input or
additional API budget is needed for that local next gate.
