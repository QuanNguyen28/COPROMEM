# Cycle 7 preregistration: repair the common no-memory interface

Recorded 2026-09-16 after the complete cycle-6 audit and before any cycle-7 paid
call. Branch `codex/copromem-research-loop`, HEAD
`18025102c010e85f26b0b3fb1144a1cb684b587e`; uncommitted exact sources will be
snapshotted by the runner. Config:
`research/configs/cycle07_appworld_source.json`.

## Hypothesis and competing explanation

Cycle 6 supplied zero native successes and extensive serialization/discovery
failures. A common public onboarding prompt and raw-Python action format may make
the same small fixed team capable of meaningful tool interaction and mixed native
outcomes. The strongest competing explanation is inadequate model capability or
horizon rather than those two interface problems.

This is baseline engineering, not a learned-memory method. The new prompt
contains human-supplied public interface knowledge. If it helps, no part of that
gain may be attributed to induced contracts, and its decisive instructions must
be available to all future arms and static controls.

## Changes, fixed quantities and contamination controls

Change only the declared prompt/output protocol:

- Both roles receive the same public onboarding, including real helper API names,
  simulated identity/credentials, incremental documentation discovery and correct
  completion semantics for answer-seeking versus mutation tasks.
- The executor is asked for a small raw Python program, not Python escaped inside
  JSON. Explicit fence/JSON compatibility parsing is logged; malformed programs
  are never silently repaired or supplied by the harness.
- The planner still produces a short JSON handoff. The team and role order remain
  fixed, with normal error feedback and no added contract, memory or recovery arm.

Everything else retains the registered cycle-6 setting: four build scenarios,
two replicates, 15 steps, seed schedule 61, environment seed 100,
`mistralai/ministral-3b-2512` through pinned `mistral`, temperature zero,
384/768 planner/executor token caps, 24,000-character public-history budget and the
same per-entry truncation policy. The worker image remains
`sha256:93dc39090e9fdf27cd1ba2bf9a93fcb68a68ef19fadfd45ac20cfc3cd1a3a2d5`.

Use a new cycle ID, request-cache namespace and output root
`artifacts/research/cycle07_appworld_source`; do not overwrite cycle 6. Budget:
USD 0.25, maximum 300 HTTP attempts including retries. At most 240 completed
planner/executor calls. Stop on provider/infrastructure failure and retain all
partial evidence. No prompt/model/sample changes after observing cycle-7 results.

The exact four build task IDs remain 27e1026_1, b7a9ee9_1, 60d0b5b_1 and aa8502b_1.
The prior group-disjoint reserved dev/audit/evaluation allocations remain unopened.
The whole oracle-used scenario 07b42fd is still excluded. Reusing build tasks is
development, not fresh generalization evidence. There is no official final-test
run and no privileged source solution.

## Outcomes and gates

Primary metric remains the number of build scenarios with both native-success
and native-failure episodes that pass independent tested-state/public-history
replay and equal native scoring. Zero mixed scenarios rejects the sufficiency of
this source protocol for same-task outcome-contrast induction. If every task
succeeds, the source also lacks failure contrast; that is not a learned win.

Secondary descriptions: all task outcomes, local errors, AST failures, formatting
fallbacks, literal API call sites, output truncations, real provider usage and
ledger cost. Raw-format fallback counts are not directly equivalent to the old
JSON-format fallback rate. Native task success, not formatting success, is the
substantive collection outcome. Repeat independent final-prefix replay and native
evaluation for each episode; unsupported or mismatched state remains reported
and ineligible rather than quietly removed from the sample.

There is no claim that changes relative to cycle 6 are a checkpoint-locked causal
effect: upstream prompts/generations differ, both interface changes are bundled,
and service stochasticity remains. No beneficial/harmful treatment-flip inference
or significance claim is registered. Later contract experiments must fork from
the exact same saved public environment **and planner artifact**, include strong
static and equal-compute controls, and measure recovery effects independently.

## Readiness and next decision

Implementation and configuration are ready. All 119 tests and Ruff pass.
Re-auditing cycle 6 under the extended parser reproduces exactly its complete
audit report ID, demonstrating that legacy evidence was not reinterpreted.
No cycle-7 paid call has been made at this preregistration timestamp.

After collection choose one KEEP/REVISE/KILL/PIVOT decision on source adequacy.
Usable mixed outcomes permit inspecting build-only candidate public defects, not
automatic admission. Continued inability to perform public tool actions motivates
a separately registered stronger-backend sensitivity test. Successes without
failures require a prospectively expanded source protocol rather than selected
handmade negative examples. No main benchmark grid or submission-readiness claim
is authorized by this small collection alone.

Run from the repository root:

```powershell
$env:PYTHONPATH = 'src'
python -u -m copromem.stateful_source --config research/configs/cycle07_appworld_source.json --env .env
```
