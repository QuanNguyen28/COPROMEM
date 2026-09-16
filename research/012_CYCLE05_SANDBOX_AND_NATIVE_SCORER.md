# Cycle 5: isolated prefix replay and native scorer validation

Date: 16 September 2026. Branch `codex/copromem-research-loop`; original HEAD unchanged.
Decision: **KEEP the bounded prefix-replay infrastructure**. This does not promote
the learned method or establish a scientific performance advantage.

## What changed

Implemented `stateful_adapter.py` and a small, isolated Docker build context under
`research/containers/appworld/`. The host exporter copies only explicitly selected
train task specifications/database changes, public API documentation and native
base databases. It excludes task ground-truth directories and refuses to overwrite
an existing bundle. The diagnostic bundle contains 59 files for `07b42fd_1`.

The execution worker accepts a bounded task/seed/action request, runs one fresh
AppWorld process and records public outputs separately from harness-only state.
The state fingerprint includes saved database-change files, serializable new
Python bindings, the native clock and Python random-state digest. Unsupported
namespace objects invalidate a checkpoint comparison instead of being ignored.

`public_observation()` uses an explicit field allowlist: task/instruction, action
history and native completion flag. It omits state fingerprints, raw database
snapshots and native evaluation results. Unit tests cover this separation.

A separate evaluator process accepts a task ID only, uses the unmodified native
`evaluate_task`, and mounts both inputs and agent output read-only. Its privileged
ground-truth access is not available to the execution worker. Native evaluation
does not rewrite the recorded agent state; the offline audit checks the files.

## Actual isolation, not only a proposed command

Docker Desktop was installed but stopped. Its local engine was started in the
background for this task. The tested runtime configuration was independently
inspected after execution:

- Network mode: `none`.
- Read-only root filesystem: `true`.
- Privileged container: `false`.
- Dropped capabilities: `ALL`.
- User: `10001:10001`.
- Security option: `no-new-privileges`.
- Declared limits: two CPUs, 2 GiB memory, 128 processes and bounded temporary storage.
- Native syntax/runtime guards remain enabled; each action has a 15-second timeout.
- Only benchmark data and one new run-specific output directory are mounted.
  The project workspace, Docker socket and `.env` are not mounted.

The worker checks for credential-like environment entries and disables dotenv.
It adds a shared public-action syntax policy rejecting filesystem tools, arbitrary
imports, implementation internals and ordinary introspection. This is an action
interface restriction shared by all future arms, not a formal proof that arbitrary
Python is secure. The container protects user files/secrets; native simulator
databases remain present for AppWorld and must not become extra agent tools.

A whole-worker timeout is supervised outside the container. Cleanup now verifies
the research label and unique output ownership label before killing a container;
a coincidentally named unrelated container is left untouched. Stopped diagnostic
containers, images and native outputs have been retained. At the completed checks
no execution/evaluation containers remained running; the Docker engine stays
available for the next cycle.

## Preregistered fixtures and observed results

The configs are under `research/configs/cycle05_*.json`. All use the previously
selected train task and seed 100; no model call or task-outcome selection is involved.

| Fixture | Repetition evidence | Native score / meaning |
|---|---|---|
| Empty prefix | `empty-a` and `empty-b`: identical observations, DB files, namespace, clock and random-state digest | Both native failures; 1/5 checks pass |
| Mutating prefix | `mutating-a` and `mutating-b`: same random draw, variable change and completion-state mutation | Both native failures; 2/5 checks pass despite a true completion flag |
| Unicode output | `unicode-a` and `unicode-b`: same host/worker request digest and output | Both native failures; 1/5 checks pass |
| API error followed by continued execution | `recovery-a` and `recovery-b`: matching recorded error at action 0, then matching continued public state and counter | Both native failures; 1/5 checks pass |
| Forbidden filesystem action | `forbidden-a`: rejected before AppWorld action execution | Expected policy rejection, not a task-performance result |
| Infinite-loop action | `timeout-a`: native timeout after 15 seconds, logged as an action error; container closes normally | A completed worker process is not the same as a successful action |
| Official reference solution | Privileged `oracle/reference-a`: 5/5 native checks pass | Scorer positive control only; ineligible for induction and method comparisons |

The empty-prefix state digest is
`bcb3f71aa41af3076b6fe95d57e847c8e76b8a19c3d50ed445a1392ac53f73d4`.
The mutating-prefix digest is
`b6079697eba4afbb955681cd0a81301f23fd945cd0dcdd05f65be7f248235a88`.
The error/recovery-prefix digest is
`f0380a013eada00f2b5bdbfabfba839876e2a657b3bdbb870d5c6274a1f21760`.
These identify this diagnostic state, not a claim of cross-task equivalence.

### Expected action errors versus a broken probe

An unexpected error invalidates a replay probe. However, a real baseline must be
allowed to observe an API error and recover; rejecting every trajectory containing
an error would artificially weaken no-memory/self-repair controls.

The comparison therefore accepts explicit `expected_error_indices` from the
already recorded trajectory. Both continuations must reproduce exactly those
errors, the public outputs and the full tested state fingerprint. Missing errors,
new errors or a different state still reject the comparison. Tests cover all three
cases. Equal error strings alone never establish a valid checkpoint.

### Reference solution is deliberately privileged

The oracle follows the invocation in official `appworld.verify`, restricted to
this one already-used train diagnostic. Ground truth is loaded in that separate
process; no solution code or privileged data enters the research-agent inputs.
The native guards remain enabled. Its result is explicitly marked
`privileged_oracle=true`, `eligible_for_induction=false` and
`eligible_for_method_comparison=false`.

This positive control establishes that the native evaluator can recognize a
completed reference task. It must not be reported as a CoProCon success or used
to train a contract. The entire scenario group `07b42fd` must be excluded from
future source/development/audit/evaluation selection for the new method pilot.

## Reproducibility and fixes made during the diagnostic

The public Python base image was resolved and pinned to
`python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea`.
The released AppWorld package remains `0.1.3.post1`. The resolved package versions
and wheel hashes are archived in `cycle05_stateful/environment/appworld_install.json`.
The actual execution worker/evaluator source used by the first runs was copied
from their immutable images into the same environment archive.

Runtime image IDs are preserved in every worker/evaluator command record. Earlier
images are not relabelled as a later implementation. The first paired fixtures use
`sha256:095b04624b7aafce24ea5887595cf75a417941e7e07cfcaaea68cd0aee3f5a10`;
the Unicode/error-recovery fixtures use
`sha256:1114b817850444c8f458a0d731d43a06ee5af50e59175b82c78a73b831e39f99`.

The worker initially used JSON's default ASCII escaping while the host hashes
canonical UTF-8 JSON. This would reject non-ASCII requests. It was corrected before
the Unicode integration runs, and a cross-host/worker hash regression test was
added. The earlier ASCII fixture results are unaffected and retained.

An exact Linux-amd64/Python-3.12 wheel lock was generated from the observed install
report. The Docker recipe now uses `--require-hashes`. This lock is platform-specific;
it must not be presented as a Windows or arbitrary-Python environment lock. The
locked rebuild has a separate image tag and will be checked before future use.

## Data grouping and remaining limits

Read-only inspection of the official train ID list finds **90 tasks in 30 scenario
groups, three tasks per group**. Native `task_id_to_generator_id` identifies the
group using the prefix before `_`. The next pilot must split by scenario group,
not merely by full task ID. No test-task content was inspected for this work.

The tested native clock stays fixed at `2023-05-18T12:00:00`. The released default
disables agent datetime changes, and that option was not relaxed. These checks do
not prove replay after an explicit harness clock advance. They also do not prove
correct handling of every mutable module, overwritten initial binding, custom
function/closure, long action prefix, other app or task family. Broader supported
state must be validated or constrained symmetrically before it is accepted.

The common syntax policy is a harness adaptation, not an exact reproduction of
every native coding-agent baseline. Baselines must not be selectively restricted
or denied ordinary self-repair while the learned method receives it.

## Cost, decision and next experiment

Cycle 5 used **zero LLM/API calls and zero additional model charges**. The paid
research total remains 198 completed generations, USD 0.00515617 settled usage
and USD 0.00621667 charged/reserved. Current local verification: 94 tests pass,
Ruff checks pass, and protected document hashes remain unchanged. No commit or
push was made.

KEEP the bounded sandbox/replay/scorer infrastructure. The strongest alternative
explanation remains that these simple authored fixtures are easier to reproduce
than real stochastic multi-step agent traces; they do not establish method value.

Next: finish supported-state and live-controller validation, then preregister a
small **outcome-independent, group-disjoint no-memory source collection** with a
fixed planner/executor workflow. Preserve API errors and baseline self-recovery.
Keep all privileged oracle outputs out of source evidence. Use the same bounded
provider ledger, a new cycle ID/source snapshot and a maximum USD 0.25 pilot cap.
Only after observing genuine repeated public-state defects should the stateful
contract representation be tested against static and equal-compute controls.

The full research objective is still open. No learned quality/efficiency win,
cross-domain transfer result or submission-readiness claim is justified.

## Locked rebuild confirmation (later same day)

The hash-locked rebuild completed as
`sha256:c24cc87e56db2ef7a636b69c634f3b375f8c749d183e5f93ec551f0ceb1e938f`
(`copromem-appworld-worker:cycle05-v6-locked`). Its `pip check` passes. Comparing
the original and rebuilt install reports finds 80 packages in each and zero
differences in package names, versions or selected wheel hashes.

`locked-mutating-a` and `locked-mutating-b` both reproduce the earlier mutating
state digest `b6079697eba4afbb955681cd0a81301f23fd945cd0dcdd05f65be7f248235a88`.
Their separate native evaluators agree on failure with 2/5 checks passing.
Exact worker source and the rebuilt install report are retained under
`cycle05_stateful/environment/locked/`. This is a concrete environment-rebuild
check, not merely a list of dependency versions. No additional model cost.
