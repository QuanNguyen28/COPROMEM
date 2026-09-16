# ExpeL native ALFWorld environment gate

Recorded 2026-09-16 while the separately frozen cycle-13 edit search runs. This
independent baseline task does not modify its source, model, candidates or data.
Same research branch/HEAD; preserve vendor code and all prior evidence.

ExpeL currently passes dependency/CLI, rule-parser and real-embedding retrieval
fixtures. It has not yet executed a native benchmark environment in the isolated
compatible image. The next gate checks that environment/action/scorer path with
one train-only fixture and no model generation. It is not a published-score
reproduction, learned policy, or benchmark performance comparison.

The unchanged vendor ALFWorld wrapper creates an `AlfredTWEnv`, selects one game,
normalizes `put ... in/on ...`, and terminates after consecutive identical
actions. Its reward comes from native `info['won']`. These native behaviors must
be recorded when later designing a faithful shared adaptation; they cannot be
silently replaced and still called exact reproduction.

## Data/version plan

ALFWorld 0.3.5 is installed in the pinned ExpeL full image. Its official tag
resolves to `9da74e4a7af532d4aea9b042628bc759a1fab0de`. The
[official download script](https://github.com/alfworld/alfworld/blob/9da74e4a7af532d4aea9b042628bc759a1fab0de/scripts/alfworld-download)
uses the 0.2.2 release's JSON, PDDL and generated TextWorld archives. Download
only those public text-data assets, not detector/agent pickle checkpoints.

Pin these observed GitHub release asset IDs and sizes before downloading:

| Asset | ID | Bytes | Last updated |
|---|---:|---:|---|
| `json_2.1.1_json.zip` | 112282473 | 72,018,818 | 2023-06-11 |
| `json_2.1.1_pddl.zip` | 112282926 | 34,881,784 | 2023-06-11 |
| `json_2.1.1_tw-pddl.zip` | 154128788 | 45,059,629 | 2024-02-29 |

The generated-game archive was replaced after the original ExpeL release; an
older asset remains separately named on GitHub. Thus current default data are
**not assumed to be the exact historical paper snapshot**. GitHub supplies no
digest for these legacy assets. Record downloaded SHA256 values as an immutable
local manifest, not as an independently published upstream checksum. Future
reuse must verify them. Retain archives and failed partial downloads.

List archive paths first; choose one supported train task by hash of
`[160906, relative_task_directory]`, excluding only path patterns the native
collector rejects (`movable`, `Sliced`). Require matching JSON/generated-game
entries. Do not inspect outcome/solution contents to choose the task or replace
it after failure. Extract only this task's text files with path traversal,
symlink, extension and size checks. Validation/test task contents remain unopened.
Fetch the two engine logic files from the pinned source commit and verify they
match the installed package before use. No archive Python or weights are executed.

## Native probe boundaries

Use the unchanged `envs.alfworld.alfworld.AlfworldEnv` in the existing full
Python-3.9.17 image, vendor and selected data read-only, network disabled, user
10001, dropped capabilities, no-new-privileges, bounded CPU/memory/PIDs and a
supervised timeout. No credentials, project workspace, socket or AppWorld data
are mounted. Temporary engine files remain inside a bounded disposable runtime
directory; preserve probe logs and container evidence.

Keep native evaluation mode but point its dataset path at the selected **train**
fixture. This is a declared component-test path override, not official test
evaluation. The native ALFWorld training/DAGGER mode attaches an expert-plan
wrapper; evaluation mode does not. Do not request or expose expert plans, policy
commands, internal facts, game JSON or solution trajectories to an agent.
There is no agent in this gate: only predetermined neutral diagnostic actions.

First confirm package/logic integrity and reset with no outcome-guided action.
Then exercise the native wrapper with `look`, `inventory`, `inventory` and record
its observation/reward/termination/step results. This tests ordinary feedback,
native repeated-action termination and non-success scoring; it does not try to
solve the task. Repeat from a fresh isolated instance and compare observable
behavior. Do not infer full environment checkpoint equivalence or a successful
policy from this simple fixture.

KEEP only the bounded environment/wrapper gate if clean reset/action/reward and
repeatability checks pass; otherwise REVISE dependency/data/runtime compatibility
without changing vendor logic or hiding failures. A real model-backed native
rollout, tokenizer/prompt/insight wiring and shared adaptation still follow.
External model cost: USD 0. No submission-readiness claim is permitted.

## Acquisition and host path-check result

The three text archives were downloaded and retained. SHA256 values are:
`25171f16e20ad7b048c47275c45b0babf3aa1cbab29cec97387922350a9844bc`,
`913942ebed06659ea0da2f8122512d98bc6add30d84961ca803132d8fbcad585`,
`d376c4bbb097c068528a2a9805e358e4cd14bc75c4d68a24e5141aebd234ef67`
for JSON, PDDL and generated-game archives respectively. Selection considered
4,639 matching supported train paths and chose
`json_2.1.1/train/pick_and_place_simple-CD-None-Shelf-326/trial_T20190910_060853_032012`
by the declared hash. Exactly three task text files were extracted. Manifest:
`data_manifests/e75ee8fc3b33ca7a4f905de141bb687eff85abf76c9282ccf594c4a9a40784ad.json`
under `artifacts/research/alfworld_native_probe_20260916`. Task contents/outcomes
did not participate in selection; official validation/test contents are unopened.

The first host test run exposed Windows `ZipInfo` normalization: constructing a
member with a backslash normalizes `filename` before the original check sees it.
That authored test failed (five passed); the shell continued to the downloader
because separate PowerShell command statements do not stop on a nonzero process
exit. The three official selected paths were nevertheless within the validated
root and used ordinary forward slashes. No file escaped the output directory.
The check is now strengthened to inspect both `filename` and `orig_filename`.
The original failure is reported rather than deleting/replacing data. Cached
assets/extracted files will be reverified, not downloaded or overwritten again.

All six path/selection tests now pass with clean lint. Cached data revalidation
returns the identical manifest above; no extraction or asset replacement occurred.

## Initial native runtime failure and scoped repair

Both fresh native probes reached the selected game but failed during engine
initialization, before diagnostic actions. Records in the ExpeL probe store:
`f31175b596a816a010a05bcb25472e60baff2ab8e7d5bbc8a5d49963b1fdb2dc`
and `e5d9d9f093eea211a20908e55865d3f9afd353aeea8beee0e3c69532d8d1e4b2`.
The installed logic hashes already matched the pinned source. The failure was
`libdownward.so: failed to map segment from shared object` under `/tmp`.

Inspection of the installed `fast_downward/interface.py` confirms that it copies
the installed library into `tempfile.TemporaryDirectory()` and then loads that
copy through `ctypes`. The no-execute `/tmp` mount prevents this legitimate native
library mapping. The inspected package source is retained under
`alfworld_native_probe_20260916/installed_sources/fast_downward_interface.py`.
No vendor/environment code or scorer is patched.

The next runtime adds a separate **128 MiB executable tmpfs** at `/native-lib`
with `nosuid,nodev` and `TMPDIR=/native-lib`, solely for this native baseline
fixture. The ordinary `/tmp` remains no-execute. Network isolation, read-only
root/vendor/data, unprivileged user, capability restrictions and resource limits
remain. This container runs only the authored neutral fixture and installed
native engine, not generated agent code. AppWorld worker policy is unchanged.
The mount/runner/fixture revision gets a new immutable probe identity; the two
initial failures remain archived. No paid request or solved-task claim is made.

## Completed bounded native gate

Both revised probes exit 0. They invoke the unchanged ExpeL wrapper and native
TextWorld engine, reset the selected train task, and execute the three neutral
actions. Structured public observations, rewards, termination and step counters
are identical across the two fresh containers. The installed logic files match
the pinned source hashes (`e64e8c...1f386e46` for PDDL and
`d955e6...7c5b361b` for grammar; full values are in the raw probe reports).

Probe IDs under `expel_native_probe_20260916/native_probes`:
`b40b54de93e2ad2d38ecfd0377a830ccdc9640eb9f6e94423733f0efd96e9161`
and `2734fea739b65953398aed9d1fc14347762ff944b7ec05c2844c946cdfb42f67`.
The independent structured comparison is
`alfworld_native_probe_20260916/native_pair_audits/520b9320832757d9e32b3ffcf79fb17a1a8c5193b2d078d81a54e3f53b819ef8.json`.

The task is not solved by `look`, `inventory`, `inventory`, as expected. All
rewards are false. The repeated inventory action sets native wrapper termination
true at next-step index 4, while `truncated` is false: the wrapper subsequently
recomputes truncation from its step counter, overriding its earlier repeated-
action assignment. This observed behavior is retained, not patched. The native
information keys are `admissible_commands`, `extra.gamefile`, `won`; expert-plan,
policy-command and fact fields are absent. No model received internal game data.

Decision: **KEEP** this bounded native environment/action/reward gate. It upgrades
ExpeL beyond import/retrieval-only checks, but does not reproduce its task-solving
policy, insight learning, production prompt/tokenizer/model wiring or paper score.
The compatible environment and current default data remain explicitly adapted.
No paid model call occurred, and all containers/probes have terminated cleanly.
