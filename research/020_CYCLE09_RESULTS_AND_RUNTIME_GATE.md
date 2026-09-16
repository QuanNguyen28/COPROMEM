# Cycle 9 result and next local runtime gate

Recorded 2026-09-16 after the complete paid source run and both offline audits.
Branch `codex/copromem-research-loop`, unchanged HEAD
`18025102c010e85f26b0b3fb1144a1cb684b587e`. No commit, push, deletion or original
document modification. Decision: **REVISE** common baseline/runtime support.

## Complete cycle-9 evidence

Qwen3-Coder via the frozen DeepInfra route produced **0/8 native successes**, with
zero mixed-outcome scenarios. Seven episodes reached the 15-step cap; one stopped
at its public completion flag after 12 steps but failed native scoring. Declared
completion is not substituted for the native task metric.

There were 117 steps, 20 recorded local action errors, zero AST errors, one planner
parse fallback and no executor-format fallback. Four programs lacked a literal
API call site but contained ordinary Python calls, including printed descriptions
of work still to do. These syntax observations are retrospective diagnostics,
not proof of task progress or causal defect labels.

Seven episodes passed replay eligibility and native-score matching. The eighth,
`c09-27e1026_1-r1`, completed normally in both workers with identical state digests
and identical native scores, but both explicitly marked `oldest_release_year`
unsupported because it retained a non-finite float. The v2 JSON-based primitive
serializer cannot represent `float('inf')`. It correctly remains **ineligible**;
neither that result nor the past image is rewritten. This is a coverage limitation,
not an observed disagreement between the paired executions.

All 234 model calls and 234 HTTP attempts completed, with no unsettled attempts
or token-cap finishes. Usage: 884,103 prompt tokens and 10,731 completion tokens,
894,834 total. Settled and charged/reserved cost: **USD 0.19375710**. Cumulative
through cycle 9: 1,152 completed calls, 1,154 attempts, USD 0.41419275 settled and
USD 0.41525325 charged/reserved. The only outstanding reserves remain cycle 3's
two ambiguous attempts; local computation is not monetized.

Evidence root: `artifacts/research/cycle09_appworld_source`.

- Collection: `reports/e5af57aae45569de9d712ca3da36bbaaa7965ecf39319efdcf26b78b5ca3bb31.json`.
- Full source audit: `source_audits/b97384b2aff53f96899f59818ab2cdf16ade0949cdf2eca0135928633153599c.json`.
- Public-context audit: `context_audits/d8cc1caad641664af696b64c1a40f6971126d9c7f4758e68c71ca48fbcd9ccc1.json`.

The context audit found 101/117 boundaries with a truncated visible history item,
one boundary omitting earlier history, 16 outputs exceeding the 4,000-character
per-output cap, and two exact consecutive program repetitions. Truncation is
frequent but not established as a cause; discarded information may be irrelevant.
The archived source snapshot was unchanged throughout the paid run. All 139 local
tests and lint/format checks pass. The private key scan found zero exact-key
matches across 7,365 text/code/evidence files at the recorded scan point; this is
not an assertion about files created later.

## Skeptical interpretation

The code-specialized backend did not make this short-horizon source protocol
sufficient. This is not a learned-memory experiment, a causal parameter-count
comparison, a fair full published-baseline reproduction or a population result.
Failure to solve these tasks does not establish failure of procedural learning.
The small subset is train/build only; no reserved instructions or final-test
outcomes were used to choose a repair.

Strong competing explanations include insufficient action horizon, truncated
public documentation, failure to retain the task's semantic objective, and the
quality of the fixed planner/executor workflow. The observed switch from release
date to library-added date on a build task illustrates semantic drift, but cannot
be converted into a domain-written learned contract and claimed as induction.

Do not run a memory comparison against this still-ineffective baseline or simply
sample more models until one appears to win. Repair the common representation and
resource constraints, then test the resulting fixed workflow prospectively.

## Next local gate, before further paid source collection

Budget: **zero external-model calls**. Preserve all old images and artifacts.

1. Add an explicit typed representation for positive/negative infinity, preserving
   their sign and distinction from strings and ordinary finite values. NaN stays
   unsupported; do not silently serialize every unfamiliar object as text.
2. Version the state format and rebuild the same hash-locked AppWorld environment.
   The state observer stays harness-only. Native APIs, evaluator and safeguards
   remain unchanged; the new support is not an agent tool or memory intervention.
3. Extend the bounded action capacity to 50 for a subsequent longer-horizon
   diagnostic, with matching live-controller and worker limits. Keep per-action
   timeout/API/character and container security limits. This is a larger declared
   workflow budget, not evidence of equal-compute efficiency.
4. Verify old typed-state, alias, clock/random, error-recovery and isolation tests.
   Add sign/type/NaN rejection tests, the new horizon boundary, and live versus
   fresh-prefix runs exceeding the old 20-action limit. Include a public mutation,
   numeric infinity, retained variables and a known recoverable API error.
5. Re-execute the exact previously unsupported build prefix only as an engineering
   regression, in a new store/image. Preserve its old ineligibility. New pair
   equality/native-score invariance is required; no new successful source episode
   or learned contract may be claimed from re-labelling the old result.

Only after this gate should a separate paid protocol declare the longer horizon,
public-context presentation and cost cap. All compared methods must ultimately
share those changes. The goal remains a learned, effect-validated contract beyond
strong static/equal-compute controls; that goal is not achieved.

## Cycle 10 local gate: completed result (same day)

Decision: **KEEP** the bounded runtime extension. This separate engineering cycle
made zero model calls and did not create a new source success or learned bank.

The rebuilt immutable image is
`sha256:b5f9aaedde041e30fc4ff795ab46d47849cfc72701b9ffc8c8983fdefe36fcf6`.
Its build source ID is
`c27d1af42aec3f4219609c734137678e15d3384fdf9da5bf9294d4b5214f5053`.
The existing native dependency layer was reused unchanged from the hash-locked
recipe; only the worker source/state format and declared capacity changed.

The new `typed-public-bindings-v3-infinity` format represents the two infinity
signs explicitly and still rejects NaN. Native workers advertise their 50-action
capacity in harness metadata. The source runner checks the actual worker capacity
before any model call, and the live controller respects the image's advertised
limit (old images without the field retain a 20-action fallback). The per-action
15-second/100-API-call/24,000-character limits and container isolation remain.
Native interaction capacity is 54, and the total request parser remains bounded
at 2,500,000 characters. These are declared resource changes, not new task tools.

The authored 25-action diagnostic retains dictionary alias mutation, a function,
clock/date/set/random values, positive and negative infinity, a simulated
completion-state mutation, a known public API error, and a counter that continues
past the old 20-action limit. Its live and fresh-prefix runs match full supported
state, public history and independent native scores. The counter ends at 19 and
both infinity signs retain the expected typed values. This is not a solved task.

The exact historical `c09-27e1026_1-r1` prefix was separately replayed live and
fresh under the new image. The pair matches and is now representable, while its
public history, database hashes and native score also equal the old saved run.
The old cycle-9 episode remains ineligible in its unchanged archive. No paid model
generation or new task outcome was obtained by this regression.

Evidence root: `artifacts/research/cycle10_runtime_gate`.
Gate report: `reports/7b2840e66a2ef208ed62ea788573e54481052ffb0d96960512b3598ff431891a.json`.
Both runtime cases passed, alongside 143 unit tests and clean Ruff lint/format
checks. The native long-prefix fixture has 25 actions; 50/51 boundary behavior is
unit-tested, not claimed as a full 50-action native task experiment. Arbitrary
Python state equivalence and all semantic side effects remain outside this
bounded evidence.

Next: declare a shared longer-horizon/public-context diagnostic before paid
generation. Keep the backend, source groups, native scorer and all methods'
information access fixed. No promotion to a memory-arm comparison is warranted
until the common workflow supplies useful outcomes and independently validated
intervention evidence.
