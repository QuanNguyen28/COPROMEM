# Native adapter and provenance audit

Date: 16 September 2026. Branch: `codex/copromem-research-loop`.
Parent commit remains `18025102c010e85f26b0b3fb1144a1cb684b587e`.
This record appends to the earlier Windows preflight and research specification.

## Hypothesis and scope

Before any stateful learned-agent pilot, verify whether native state restoration
is sufficient to create matched continuations. The smallest check uses one train
task, reviewed fixed Python statements and no LLM-generated code. It is an adapter
diagnostic, not an agent policy, task-solving attempt or benchmark score.

The task was selected as the lexicographically smallest train ID, `07b42fd_1`,
before observing its outcome. Hidden ground-truth loading was disabled. No final
test-task content was inspected. Every run used a unique output directory because
AppWorld initialization can clear an existing experiment directory.

## Environment and isolation

Native Windows and Ubuntu WSL environments both installed the same released
`appworld==0.1.3.post1`. Dependency resolution artifacts are saved as
`artifacts/research/appworld_install_20260916.json` and
`artifacts/research/appworld_linux_install_20260916.json`. Both environments pass
`pip check`; that does not prove runtime compatibility.

Windows uses local Python 3.12. The Linux environment uses Ubuntu Python 3.12.3.
System `ensurepip` was unavailable, so the first Linux venv creation failed. That
partial directory was preserved. A separate environment was created using the
official PyPA standalone virtualenv zipapp without sudo/global package changes.
The downloaded zipapp SHA-256 is
`2DFDB6785B762B8A7A7A31D413C16516AA785552D05F61435B072FDE1CB340CC`.
The successful Linux environment is `.research-envs/appworld-linux-013b`.

Package caches/data are repository-local and Git-ignored, not deleted. Only the
package apps/tests were unpacked; no benchmark test-task inspection was performed.
The Docker daemon was not started. **This WSL process is not an adequate security
sandbox for arbitrary model-generated Python.** No such code was executed.

Syntax/runtime safety guards and the 15-second native action timeout remained
enabled. A 55-second external supervisor bounds each diagnostic child process
and preserves stdout/stderr outside AppWorld's process-global patches. API-key,
token, secret and password environment entries are removed. Python-dotenv is
explicitly disabled so AppWorld cannot reload the repository's `.env`.

## Observations, including probe mistakes

All raw supervisor records are under
`artifacts/research/appworld_preflight_20260916/preflight_records/supervisor/`.

| Run | Observed result | Permitted interpretation |
|---|---|---|
| `native-state-v2-supervised` | Windows execution fails on absent `signal.SIGALRM`; parent records the exception | This released timeout path does not work in the tested Windows configuration |
| `native-linux-state-v1` | Execution reaches restore, then cleanup fails in the clock/freezer lifecycle | Import/install success is insufficient for adapter readiness |
| `native-linux-state-v2` | Partial logging exposes restored database status but persistent Python variable; cleanup still fails | Native database state and Python interpreter state are different |
| `native-linux-fresh-v1`, `v2` | Fresh-process public state/namespace match, but the clock probe itself returns an error | Do not count the matching clock errors as time restoration |
| `native-linux-state-v3` | Corrected clock query; database completion resets, Python variable remains changed, cleanup fails | Database-only restore is not a full paired checkpoint |
| `native-linux-fresh-v3`, `v4` | Both fresh processes complete/close normally and produce the same validated public prefix fingerprint | Fresh-process replay is a feasible direction for this tiny authored prefix only |

The clock probe mistake was ours: AppWorld's namespace contained the `datetime`
module, but the first probe called `datetime.now()`. The corrected call is
`datetime.datetime.now()`. The helper now parses the returned ISO timestamp and
rejects execution-error strings; regression tests cover this exact failure.
All earlier reports remain preserved rather than silently relabelled as successes.

The corrected restore run recorded:

- Completion status after the authored mutation: `true`.
- Completion status after native `load_state`: `false`.
- Python `probe_counter` after restore: `2`, although its saved value was `1`.
- Clock before/after: `2023-05-18T12:00:00` in this probe.
- Context-manager cleanup: `AttributeError` in freezegun, followed by a cleanup
  `IndexError` in the exception hook.

Equal clock readings here do **not** prove restoration after an explicit clock
advance; that was not tested. Native source inspection shows `load_state` calls
global close/reset machinery and recreates API bindings. The observed freezer
cleanup failure is consistent with a lifecycle mismatch, but attributing it
uniquely to AppWorld versus a resolved dependency version requires further tests.
No vendor code or dependency pin was changed to hide this failure.

The corrected fresh runs both produced fingerprint
`cbc8949e95e5d7dda664abfea902d5e6c35e9f6ba392360e3ecd78f7a1fffb05`.
Their namespace initially lacked `probe_counter`, the authored prefix set it to
`1`, the clock matched and completion remained false. This checks a narrow public
state/namespace reconstruction. It does not compare full databases, random-state
restoration, lengthy mutation prefixes, collateral changes or native evaluation.

## Decision: REVISE adapter; retain the research pivot as a hypothesis

Do not promote native `save_state/load_state` to a full scientific checkpoint.
Use fresh arm-specific processes and deterministic, recorded prefix replay as the
next adapter implementation candidate. Check every replayed observation and
relevant environment state before running a treatment. Any divergence must
invalidate that comparison rather than be ignored.

Before paid stateful collection, the adapter still needs: an isolated environment
for model code; a shared fixed workflow/tool interface; mutation/reset and
cross-arm tests; evaluator/collateral-effect invariance; task-family split policy;
bounded replay cost accounting; and public-only contract inputs. A two-run prefix
fingerprint is not enough to scale or to claim learned-method efficacy.

## Resume protection and exact-source limitation

Both real pilot CLIs now bind a run to its recorded source/environment provenance
before dataset/provider/credential access. A changed code/environment resume is
rejected with instructions to create a new preregistered cycle or audit offline.
The cycle-2 CLI was deliberately invoked after this change: it raised the expected
`IntegrityError` before any provider call. Existing records were not overwritten.

New pilot runs also archive the actual Python source text, not only hashes.
Earlier cycles stored source hashes, raw prompts, responses, checkpoints,
configurations and outcomes, but did not snapshot every intermediate uncommitted
source version. Consequently exact reconstruction of those original source trees
from the run directory alone is **not guaranteed**. Do not describe the old
archives as fully reproducible source releases. Their recorded generations,
outcomes, costs and current-miner reanalysis remain independently inspectable.

The completed-archive integrity audit was rerun on all three paid cycles and
passed: 198 completed generations, 200 attempts, USD 0.00515617 settled usage,
USD 0.00621667 charged/reserved. The current all-success-veto miner still finds
zero candidates in each induction corpus. No additional paid calls were made.

## Engineering verification and preservation

The local suite now has 76 passing tests. Ruff lint/format checks pass. New tests
cover old-format provenance compatibility, changed-code rejection and invalid
clock-output rejection. The two original protected document hashes still match
the initial-state record. An actual-key leak check across 1,101 relevant source,
test, research and artifact files found zero matches at the time of that scan.

This is progress in experimental reliability, not completion of the research
objective. A nonempty useful learned bank, strong static-control advantage,
broader benchmark evidence and a defensible novelty claim remain unestablished.
