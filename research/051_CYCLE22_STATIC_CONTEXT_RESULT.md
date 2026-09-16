# Cycle 22: public context improves a standard name-checking control

Recorded 2026-09-16 after the complete registered comparison and exact CLI
repetition. [Protocol 050](050_CYCLE22_LOCAL_ERROR_AND_STATIC_CONTEXT_PROTOCOL.md)
remains frozen. Branch `codex/copromem-research-loop`, HEAD
`18025102c010e85f26b0b3fb1144a1cb684b587e`; no commit or push.

## Result and decision

All 14 registered action/checkpoint records are eligible: five public outputs
report an uncaught missing-name error and nine report no uncaught execution
error. There are no unknown-coverage, ambiguous-label or checker-failure
exclusions. Both configurations use the unchanged installed Ruff 0.16.2 F821
checker, isolated configuration and a Python 3.12 target.

| Action-level local-error diagnostic | A: only framework name | B: public entry context |
|---|---:|---:|
| Detected reported NameError | 5 | 5 |
| Missed reported NameError | 0 | 0 |
| Warning without reported NameError | 1 | 0 |
| Clear without reported NameError | 8 | 9 |

Both configurations identify the actual missing name in all five error cases.
Context eliminates the warning for `liked_songs` in one initializer-deletion
variant because the exact public entry observation confirms that binding exists.
The same program at the other origin still warns and actually fails with that
missing name. Unknown names are not silently treated as absent.

Primary result: **one fewer false warning, with no lost true detections**.
Decision: **KEEP this context-aware standard checker component for controls**.
This is ordinary static-analysis value, not learned-memory value. The presence
declarations are analysis-only `name = None` stubs: they never execute, never
change the native action and make no claim about the real binding's value.

## Complete denominator and the remaining failure

The fixed corpus comprises all ten cycle-13 variant/origin cells, all three
cycle-21 factual target actions, and the passing cycle-18B new-task edit. Every
record is retained. The error indices are 2, 3, 5, 8 and 9; the eliminated false
warning is index 4. These are correlated development records on two already
inspected scenarios, not 14 independent tasks or a statistical generalization
test. No superiority interval or population-level claim is warranted.

Crucially, **four of the nine checker-clear actions still lead to native task
failure**: indices 0, 1, 10 and 12. The first two omit the producer loop; the
last two are the original failed-source target actions. Native task outcome is
an audit column, not the local NameError label or a checker input. This result
does not establish that any particular semantic invariant is the unique cause.

F821 is not a sound definite-assignment analysis or a completeness, correctness,
termination, applicability or recovery verifier. Passing this component cannot
admit a procedural contract. Conversely, a standard checker solving these five
name errors removes them as evidence of a special learned-method capability.

## Reproduction evidence

Main store: `artifacts/research/cycle22_static_name_check`.
Separate tool preflight: `artifacts/research/cycle22_checker_preflight`.

| Record | Content digest |
|---|---|
| Protocol | `193aae7253bae8239484d4e1414fb50bacaa2eeaf067bd5efa63a85179d7cad5` |
| Frozen comparison sources | `fce4c9d6583f8bee330b6e6d9442d116abc14950d89617f59c1deba04088a0a6` |
| Tool profile | `800b496d3fe2bb3d07f69e81e4bc8557e89875619b2c7e9de93f1859ac0b4df6` |
| Complete report | `44089b0c774a60e7f942675dbccb0b77e3d2e81f6fdeb68af51205a8383dfe8a` |
| Independent-count / exact-repeat audit | `29a92ada86516322f635750c6d685e2dc6d6190cc59834f5f5471b071cf16fa5` |
| Auditor source snapshot | `cd8ad3a98a874814405e0adbddb6945ea4200e7e07ad33360e4a19ea982d0af2` |

The executable SHA-256 is
`0cf602e931f311581bce0b1dfc8d5e30717d96af54c65d7b89a9a8d4497b0eeb`.
The preflight stores raw version/rule metadata and two constructed ASCII/Unicode
fixtures before the main comparison. It is component inspection, not a benchmark
result. Analysis uses stdin with a virtual filename; no benchmark program runs.

The audit rebuilds public inputs from independently checked source executions,
binds each context to the exact planner/checkpoint and supported pre-action
state, verifies executable/source identities, reconstructs original-line
diagnostics and independently counts metrics. It repeats all 28 CLI checks and
requires equality of complete raw process records, including argv, cwd, stdin,
stdout, stderr and exit status. All attempts/results are inventoried; unresolved
attempts are not silently restarted. This repeats the measurement, not the
scientific sample.

```powershell
$env:PYTHONPATH='src'
python research/scripts/run_static_name_check.py --audit-only
python research/scripts/audit_static_name_check.py
python -m pytest -q
```

Run materializing audits serially per store. The commands verify the saved
comparison/repetition when the evidence already exists, rather than making an
unrecorded additional experimental sample. Full verification currently passes
**404 tests**, including the new source-binding, local-label, unknown/absent,
stub, parser, denominator and raw-repetition integrity fixtures.

## Cost, critique and next step

There are 28 original and 28 repeated main checker processes, plus two metadata
and two toy-fixture processes in the separate preflight. No new native execution,
model call, API charge, recovery action or contract admission occurs. Checker
compute is not free simply because API USD is zero; cycle 21's shared observation
also remains an inspection cost for future comparisons.

Paid accounting is unchanged: USD 2.85687245 settled / 2.85793295
charged-reserved. Historical archived-donor acquisition cost remains unknown.

The strongest explanation is exactly the expected control mechanism: supplying
known existing names improves a standard lexical check. It does not validate
automatic semantic induction. The next experiment must address a procedural
failure left by this control, use genuine evidence-derived candidate logic and
include a competent manual semantic control. Training consistency on these known
cases must not be called admission, held-out transfer or reduced authoring effort.
The two local native repairs remain retained but unadmitted, and the autonomous
research goal remains active.

### Closing verification and transition

The later cycle-23 input-preflight fixtures bring the full suite to **415
passing tests**; they do not alter this cycle's frozen sources, result or earlier
404-test verification. Scoped lint has only the preserved older FURB192 warning. The research
branch/HEAD and both original document hashes are unchanged; no experiment
containers remain running and no commit or push occurred.

The [next registered diagnostic's input stage](054_CYCLE23_INPUT_PREFLIGHT_STATUS.md)
is complete, with zero generated candidates or new model calls. Its primary
construction decision is still pending, not counted as another positive result.
