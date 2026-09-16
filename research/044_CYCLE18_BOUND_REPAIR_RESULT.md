# Cycle 18B: an automatically bound repair on a second build scenario

Recorded 2026-09-16 after the complete registered experiment and independent
audit. Branch `codex/copromem-research-loop`, HEAD
`18025102c010e85f26b0b3fb1144a1cb684b587e`, original documents, frozen operators,
native workers and evaluator remain unchanged. The [043 preregistration](043_CYCLE18A_RESULT_AND_BOUND_EFFECT_PREREGISTRATION.md)
and every failed intervention remain preserved.

## Result and decision

All three fresh factual controls reproduce their original supported state,
public outputs, completion and native score. All five automatically bound edits
are executed and replay-eligible. **One edit succeeds on b7a9ee9_1**, giving the
preregistered primary metric of **one newly repaired task**. Decision: **KEEP the
local bound-repair finding**, not an admitted contract or learned-method win.

| Effect cell | Origin | Action index | Native tests passed | New uncaught error positions | Additional native API-log entries |
|---|---|---:|---:|---:|---:|
| edit-00 | c11-b7a9ee9_1-r0 | 15 | 3/4 | 0 | 24 |
| edit-01 | c11-b7a9ee9_1-r0 | 17 | 3/4 | 0 | 24 |
| edit-02 | c11-b7a9ee9_1-r0 | 19 | 4/4 | 0 | 34 |
| edit-03 | c11-b7a9ee9_1-r1 | 16 | 2/4 | 0 | 24 |
| edit-04 | c15-b7a9ee9_1-r2 | 9 | 2/4 | 0 | 2 |

The first two edits do not improve the factual 3/4 native score; the last two
retain their factual 2/4 score. These partial scores are descriptive, not a
redefinition of the primary success gate. No candidate, seed or boundary was
replaced after observing results. Five related edits are not five independent
research examples, and the three controls are not independent task replicates.

The successful edit preserves the original target input setup and automatically
maps the donor's external input name using public API/keyword correspondence.
It replaces one action at its exact saved checkpoint and leaves all later action
strings unchanged. Its full sequence has 185 native API-log entries versus 151
factually. The measured cell time is 39.079 seconds, including its native
executions/scorers; summed time over all eight cells is 298.940 seconds. This
is neither equal-tool-compute evidence nor a quality-cost efficiency result.

## Integrity and reproducibility

The independent audit regenerates all construction/provenance records and the
five-effect/three-control manifest, then checks raw native worker/scorer process
outputs, checkpoint identity, public planner/handoff identity, unchanged future
programs, final database hashes, error positions, tool counts and full accounting.
It verifies **16 native executions, 16 scorers, 40 live frames and 24 live
post-checkpoint inputs**. All live/fresh replay pairs agree. Frozen source text
equals current source at this audit. Audit execution itself makes no native or
model calls. There are no unaccounted effect cells or replacement attempts.

Root: `artifacts/research/cycle18_bound_effects`.

- Protocol: `d955c0ee41bf4af62f10ddb779252fd8c0ed12519f50fa94fcdd15e675bb4974`.
- Frozen sources: `737af64696761f67af487d3d2073162fb568e1ace8ef3c014a6bbab8c00a9d3a`.
- Report: `41f762eab2b0f87b9088e6c9234986d00c4b94245b6d87aa8a09b3bf7a6b5465`.
- Independent audit: `4c2e4986402e6f8fcb9c591b044edc410ce8f4c1510dcf7346bd1ed0c783b995`.
- Passing effect candidate: `70c1d9f82e108bd06798add563d04e35f37cca8d003fbeae811aad468cb5239a`.
- Passing program AST: `bc8fb266dc1bd4bab8c85c1a2ac0258abb4006915b0a0a9c990f64fac3ace2a1`.

```powershell
$env:PYTHONPATH='src'
python research/scripts/screen_public_bindings.py --audit-only
python research/scripts/audit_bound_effects.py
python -m pytest -q
```

Run materializing audits serially per store. The complete suite passes 308 tests.
Scoped Ruff checks report only the previously documented frozen engine's
FURB192 style warning; the new constructor, runner, auditor and tests are clean.
No native experiment containers remain running at this closing inspection.

Cycle 18 makes **zero model calls and zero new external API charges**. Previous
cumulative accounting stays at 2,464 completed calls / 2,466 attempts,
USD 2.85687245 settled and USD 2.85793295 charged/reserved. Historical donor
acquisition costs remain unknown and must not be described as zero total cost.

## Hostile-review interpretation

There are now local automatically derived repairs on **two independently
selected build scenarios**, rather than just the old aa8502b example. This is
useful progress beyond syntactic construction acceptance. It is still a
development search over repeatedly inspected episodes, not independent held-out
evaluation. The new task's originally successful source has not yet received a
matched harmful-flip guard for the proposed repair.

Post-hoc human inspection notices that both successful producer blocks perform
repeated collection calls with accumulation and stopping conditions. Their API
paths, inputs, branch structure and short-page handling differ. Recognizing this
similarity does **not** automatically infer a shared invariant, validate its
applicability or provide two supports for one contract. Generic binding/closure
also does not establish sound runtime input availability or semantic correctness.

The strongest alternative explanation remains ordinary local program repair
with additional tool work. The current estimand is an open-loop unchanged saved
continuation, not adaptive regeneration by a recovered multi-agent workflow.
There is **no learned stateful executable verifier, validated generalized scope,
admitted stateful bank, retrieval benefit or held-out advantage over strong
static/text/equal-compute controls**. Novelty and submission-readiness gates are
not met. Two successful patches must not be relabeled as learned contracts.

Next, test whether a generic, explicitly bounded executable predicate language
can derive a consistent public-code separator from the two effect-backed pairs,
and retain its ambiguity and failures against the other recorded effects. This
is a verifier-proposal/identifiability diagnostic, not contract admission or a
claim that final-task failure uniquely labels a bad handoff. The autonomous
research goal remains active.
