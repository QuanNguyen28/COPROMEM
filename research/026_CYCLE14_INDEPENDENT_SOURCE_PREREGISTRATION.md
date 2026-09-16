# Cycle 14: independent build-source extension

Registered 2026-09-16 before opening new task instructions or making cycle-14
model requests. Previous goal turn: **progress** (automatic local repair,
native ALFWorld component gate and preservation/audit evidence). The goal remains
active. Branch `codex/copromem-research-loop`, unchanged HEAD
`18025102c010e85f26b0b3fb1144a1cb684b587e`; preserve all originals and old results,
no commit/push/deletion.

## Question and strongest alternative

Can the unchanged fixed planner/executor supply additional replay-eligible
success/failure contrasts on independent training scenarios? Cycle 13 isolates
an automatically derived local producer-block repair, but its two checkpoints
belong to one task. Extra repetitions of that task cannot satisfy independent
source support, scope, admission or held-out validation.

The alternative is that the source policy remains too weak or inconsistent, or
that useful contrast is too sparse/diverse for the current induction operator.
Additional contrasts can justify investigating transferable repairs; they do
not by themselves validate any contract, common invariant or novelty claim.

Primary metric: count of **new** scenarios containing both native-success and
native-failure replay-eligible episodes. Four scenarios, two replicates each.
Zero rejects the extension as sufficient for additional same-task outcome
contrast. All-success and all-failure both lack the required paired contrast.
The denominator includes unsupported-state/provider-failure episodes; only
replay-eligible, provider-complete episodes can contribute induction pairs.

## Allocation without outcome-dependent substitution

Config: `research/configs/cycle14_appworld_source.json`.
Store: `artifacts/research/cycle14_appworld_source`.

Pin cycle 11's complete original allocation and protocol by canonical digests,
and the native train identifier manifest by SHA-256. Verify the old allocation
by recomputing it. Keep selection seed 160906, all exclusions, and the original
dev/audit/evaluation counts/IDs. Exclude **all** previously allocated scenario
groups, including the four old build groups, not merely their first task variants.
Exclude the whole oracle/diagnostic scenario `07b42fd`.

From the remaining training scenarios, take the first four in the original
`SHA256(canonical([selection_seed, scenario_id]))` order. Select the lowest
numeric task variant per group. This uses identifiers only, not task instructions,
API names, failure categories, trajectory contents or results. Freeze the exact
selection in the append-only store before exporting the selected public data.
Keep the prior build allocation in `previous_build`; it is not re-run or reassigned.
Reserved dev/audit/evaluation instructions stay unopened. Do not substitute a
task, change a seed or increase repetitions in response to outcomes.

These are new **build** tasks, never a held-out test of the existing edit. The
decision to extend source data follows an observed one-task bottleneck and is
therefore adaptive research planning, not a prospectively selected population
test. Report all eight outcomes, including failures and missing samples.

## Unchanged workflow, runtime and budget

Use the same cycle-11 fixed no-memory planner/executor: Qwen3-Coder via only
`deepinfra/turbo`, no provider fallback, temperature zero, model seed schedule
61, environment seed 100, public-onboarding-v2, raw Python, 384/768 output token
caps, 50 steps, 64,000-character context, 16,000-character outputs and
6,000-character programs. Both roles receive the same public-history-budget-v2
metadata. Provider seeds do not guarantee determinism.

Native image remains
`sha256:b5f9aaedde041e30fc4ff795ab46d47849cfc72701b9ffc8c8983fdefe36fcf6`.
Network-isolated generated-code worker, public bundle and separate native
evaluator are unchanged. No learned repair, static hint specific to a new task,
oracle code or evaluator feedback enters either role. Fresh-process replay must
agree on the bounded supported state, public outputs and native score.

Hard maximum **USD 4.00** per this cycle, below the user's USD 5 authorization;
1,000 HTTP attempts, at most 800 completed generations. Preserve per-attempt
reservations, ambiguity costs and recorded transport retries. Route price caps
remain USD 0.50 / 2.00 per million input / output tokens. Stop on the existing
provider-budget policy and report incompleteness rather than expanding budget.
Fresh endpoint metadata is archived before generation. No extra paid baseline
run is included in this protocol.

## Integrity checks and analysis

Before collection, test deterministic selection, scenario-level exclusion,
reserved partition immutability, registry/data tamper rejection, exhaustion and
unknown extension versions. Preserve legacy selection behavior. The preparation
command freezes config, code, preregistration text and selection without exporting
task contents or making provider calls. The actual run must match that provenance.
Retain all calls, raw responses, public handoffs, planner artifacts, programs,
worker frames, DB state, native scores, independent replays and failures.
No implicit restart of partial live episodes is permitted.

After termination, independently audit all source steps and replay/native-score
pairs, exact original allocation preservation, all usage/settlements and actual
public bundle task IDs. Report native success, mixed outcomes, exclusions,
completion/horizon, action/parser/provider errors and public context omissions.
No significance, population superiority or minimum semantic repair is inferred
from this small source sample. Do not pool repeated runs as independent tasks.

**KEEP** new source evidence only if at least one new usable contrast emerges and
integrity audits pass; otherwise **REVISE** the source/induction design. Any
integrity failure requires diagnosis before evidence use. A KEEP does not admit
the old pagination repair: a different task's success/failure need not support
the same condition, corrective edit or scope. No automatic admission threshold
is relaxed. Static documented checks and equal-compute recovery remain essential.

Next, apply evidence-derived proposal/effect validation to all eligible new pairs
under a separately frozen local protocol, retaining failed/no-proposal cases.
Only independently supported, scoped candidates may proceed to disjoint dev and
audit admission, followed by a frozen held-out comparison.
