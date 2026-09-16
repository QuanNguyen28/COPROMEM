# Cycle 13 result: automatically derived local producer-block repair

Recorded 2026-09-16 after the preregistered search terminated. Decision: **KEEP**
the bounded proposal/effect-validation mechanism and observed local repair. This
is not an admitted contract, learned scope, held-out gain or submission-ready
contribution. Branch `codex/copromem-research-loop`; HEAD remains
`18025102c010e85f26b0b3fb1144a1cb684b587e`. No original document, vendor file,
negative result or source trajectory was removed/overwritten; no commit/push.

## What was implemented

`src/copromem/procedural_diff.py` adds a generic, immutable `BlockTransplant` and
name-based backward producer-block proposal operator. It parses the actual
failed/successful programs and considers shared uniquely assigned top-level
bindings. Conservative method-receiver mutation and read/write dependencies
determine contiguous spans; identical blocks are rejected. The failed program's
remaining statements are preserved by AST identity. The implementation has no
benchmark API names, task IDs, pagination keys or page sizes. Concrete repair
statements/constants are copied from the saved successful program.

This syntax heuristic is deliberately not described as a sound arbitrary-Python
slicer. Aliasing, argument mutation, dynamic dispatch and general control
dependence are incomplete; unsupported nested lexical scopes are rejected.
Native effect tests, not apparent syntactic plausibility, decide local utility.

`src/copromem/stateful_effect.py` binds the exact origin environment, public
context and planner generation/artifact before executing a fixed edited program.
It requires independent replay/native-scoring agreement and supports append-only
completed-cell reuse with source binding. It rejects partial/mixed evidence.
An effect pass requires native success, completion, supported state and no new
uncaught action error. A normal action error rejects a variant; infrastructure
or integrity failures stop for explicit diagnosis.

`research/scripts/run_procedural_diff.py` freezes configuration, source and all
initial proposals before edited execution. It conducts a budgeted greedy
single-top-level-donor-statement deletion search, caches exact program ASTs and
retains failed alternatives. `audit_procedural_diff.py` independently regenerates
proposals/search decisions and verifies all native cells and saved checkpoints.

## Frozen source and result

The inputs remain the one success/failure pair from cycle 11 and the two exact
cycle-12 pre-final checkpoints. These are two histories of **one build task**,
not independent source tasks or unseen evaluation data.

Exactly one initial transplant was proposed. The `access_token` anchor was
rejected as identical; `liked_songs` yielded a replacement of failed top-level
statement span `[1,2)` with successful span `[1,5)` (zero-based, end-exclusive).
The inserted donor block initializes the page index, page limit and result list,
then retrieves/accumulates pages in a loop. The original artist-following suffix,
its variable names and its completion call remain unchanged. No corrective
program was manually authored or requested from a new model call.

The original block has one statement / eight non-context AST nodes; the inserted
block has four statements / 45 nodes. Thus **the patched program is larger**, not
a compressed version of the failed program. It replaces a smaller region than
the prior whole-program swap; that does not mean globally minimal repair.

Primary outcome: **one automatically proposed transplant passes at both origins**.
It passes all four native task checks, completes, adds no uncaught action error,
and its two live runs agree with their independent fresh-process replays. Each
origin's exact pre-action state/planner checkpoint is verified again before use.

Five distinct edited programs were tested, below the cap of twelve. This means
ten origin-specific cells, twenty native worker executions, and twenty separate
native scorer invocations. All ten replay pairs agree. There were zero model
generations or paid requests. Local simulation/CPU work is not free compute.

| Edited block | Failed-origin native checks | Successful-origin native checks | Effect gate |
|---|---|---|---|
| All four donor statements | 4/4, complete, no new error | 4/4, complete, no new error | Pass |
| Delete page-index initialization | 2/4, incomplete, `NameError` | 1/4, incomplete, `NameError` | Reject |
| Delete page-limit initialization | 2/4, incomplete, `NameError` | 1/4, incomplete, `NameError` | Reject |
| Delete result-list initialization | 4/4, complete, no new error | 1/4, incomplete, `NameError` | Reject |
| Delete retrieval loop | 3/4, complete, no new error | 2/4, complete, no new error | Reject |

The list-initialization deletion is informative: one history already has a usable
binding while the other does not. Testing only the first history would have
accepted a state-dependent simplification. Requiring both origins rejects it.
This is evidence for checking state dependencies in this case, not calibrated
scope learning. A missing runtime exception is also insufficient: deleting the
loop still completes and prints a success-like message, yet native scoring fails.

No deletion was accepted. The four-statement edit is a fixed point for the
**tested single-top-level-statement deletion operator**. Nested-loop clauses,
initialization substitutions, constants, alternative bindings and other patches
were not searched. Do not call it the smallest possible or minimal semantic edit.

The passing block adds 23 native API-log entries at either origin, versus seven
for the original failed program in cycle 12. Removing either scalar initializer
adds zero before failure; removing list initialization adds 23 at the first origin
and one at the second; removing the loop adds only one completion request. Actual
API execution is part of the measured treatment. No equal-compute advantage is
claimed, and the native calls are not external paid service requests.

## Evidence and reproduction

Store: `artifacts/research/cycle13_procedural_diff`.

- Frozen protocol: `d9746ed0cdff0370c54194d5c3885fbfa0437d1c40ccc48252ad3d7d394ee198`.
- Source snapshot: `f02a244ecfa48d0aca631000a9d2e7d3211b975264610a7fa1fa6f2396844fad`.
- Result: `reports/3b804f5a064696081627852d0eb3046e761a7dae49ec410d8ecb92d1da2a166d.json`.
- Independent audit: `independent_audits/a21610194ac635fbc5c1fdb8cd43ac8417543813c9f557bd07aaa37de2f336e2.json`.
- Passing program AST: `45c299c43e68a9e627fc074073eff39dc0118e137d6f0b66afb59572c7338db3`.

All proposals, rejected anchors, variant programs, reduction decisions, original
generation IDs, native outputs, API logs, DB state, error traces and per-origin
replay audits remain saved. The independent audit regenerates the proposal and
deletion search, accounts for every tested variant and reproduces the same audit
digest from the reusable script. It does not generate new test-task evidence.

```powershell
$env:PYTHONPATH = 'src'
python -m pytest
python research/scripts/audit_procedural_diff.py
```

The full suite now passes **197 tests**, with clean Ruff checks. Tests cover
neutral-name/API/constant changes, dependencies, suffix preservation, no-op and
unsupported-scope rejection, no host execution, immutable edits, hard search
budgets, exact checkpoint binding, corrupt evidence and strict effect gating.
These engineering checks are separate from the native outcome table above.

## Reviewer critique and novelty boundary

The new result supports a smaller **evidence-derived local code repair**, not yet
the original broader claim of induced scoped contracts improving future tasks.
The current object has no validated transferable initiation condition, verifier,
scope policy, retrieval/admission decision or cross-task recovery guarantee.
The earlier two-independent-source-task admission requirement is still unmet.

The broader operation is not new by itself. Primary-source screening confirms
that delta debugging already isolates passing/failing differences and minimizes
them with tests; GenProg performs statement-level program repair and uses
structural differencing/delta debugging to reduce repairs. Our current greedy
deletion search is not an implementation of their full algorithms. Applying a
similar operation to agent-generated programs is not sufficient evidence of
novelty. See the [updated novelty matrix](NOVELTY_MATRIX_20260916.md) for sources
and remaining distinctions that would need experimental support.

The pagination knowledge is already in public API guidance and shared onboarding.
A strong static completeness/pagination control remains mandatory. The observed
repair cannot support claims that contrast, retrieval, learned scope, runtime
verification, extra generation or human-effort reduction caused an advantage;
those components were not compared. There is no plausible population confidence
interval from one task, and repeated native executions do not increase task N.

## Next research action

The bottleneck is **independent support and transferable scope**, not more tests
on the same example. Preserve this block as unadmitted build evidence. Register
an outcome-independent source extension or another independent source task
before claiming a reusable rule; reserved dev/audit/evaluation groups must not
be silently moved into build. Derive any abstraction from saved evidence, expose
its runtime-checkable condition, and test false activation/harm alongside a
same-path static documented control and equal-compute recovery.

Nested minimization can clarify this example, but must not substitute for those
missing controls and independent evidence. The novelty claim must also survive
traditional automated-repair baselines, not only contemporary agent-memory work.
The research objective remains active and is not closeable from this local result.

## Final preservation and safety check

At 2026-09-16 04:06 UTC, the full 197-test suite passed again; Ruff lint and the
ten newly changed Python files' formatting checks passed. Branch and HEAD remain
as recorded above, ExpeL's vendor working tree is clean, and both original
`docs/CoProCon_research_doc` files retain their previously recorded SHA-256 hashes.
No research containers were running at this handoff.

An exact-byte scan for the configured OpenRouter key checked 26,749 files
(1,722,831,260 bytes) across source, tests, research, artifacts, docs, vendor and
root files: zero matches and zero unreadable files. The scan excludes `.env` and
vendor `.git` metadata; it is not a general secret detector. No key value was
printed or persisted. The append-only safety record is
`artifacts/research/safety_audits/ba8ac49a84ea70bc62cfc34a3bf1634c9c8fbb5f8fff2914303a75e8a392c10a.json`.
