# V5 engineering split amendment

## Status and scope

This is an infrastructure-only custody amendment to the continuous CoProMem v5
engineering runbook. It applies only to the new `fixed_dynamic_v5_engineering_002`
run. The earlier `fixed_dynamic_v5_engineering_001` development-only NO-GO audit
is immutable and remains valid.

The amended run is **engineering-only and exposed**. It must not be used for
efficacy, superiority, transfer, generalization, benchmark-test, or final-test
claims. Its purpose is to exercise the real provider, official upstream ReMe
service, AppWorld worker/scorer boundary, append-only ledger, continuous
CoProMem update/retrieval path, and restart path.

## Mixed-split allocation

The evaluation allocation is selected only from public task instructions and
public API shapes:

| Role | Split | Task ID | Initial structural state |
| --- | --- | --- |
| A | `dev` | `50e1ac9_1` | unknown |
| B | `dev` | `50e1ac9_2` | unknown; same frozen descriptor as A |
| C | `train` | `29caf6f_3` | compatible with the complete provisional workflow learned from train task `29caf6f_1` |

`29caf6f_3` is held out from the 32-history acquisition export. The train
inventory audit records all acquisition IDs, every unseen train candidate, and
why partial/reordered/incomplete candidates were rejected. The C descriptor is
the complete ordered operation/input-slot/output-slot signature from the fresh
warm-start schema; it contains no task-specific values or scorer evidence.

Mixed `dev`/`train` evaluation is permissible here solely because this is an
engineering exercise of continuity and compatibility mechanics. Train C is not
an independent performance holdout, and development A/B are previously exposed
engineering tasks. `test_normal` is never opened or used.

## Unchanged controls

The run keeps the four registered arms, two seeds, 30-action limit, 24 expected
scored trajectories, public descriptors, acquisition/evaluation task-ID
disjointness, locked provider route, route-role ceilings, append-only ledger,
restart/no-replay requirements, and USD 15 all-inclusive cap. The accepted
conservative bound remains USD 12.670976 (USD 11.018240 dispatchable plus a
non-dispatchable 15% contingency of USD 1.652736).
