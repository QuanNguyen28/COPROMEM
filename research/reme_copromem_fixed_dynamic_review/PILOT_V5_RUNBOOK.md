# Continuous CoProMem v5 pilot runbook

This is an engineering pilot for the real AppWorld, upstream ReMe, provider,
task-boundary merge, and restart path. It is not a statistical comparison of
methods. The pilot has three evaluation tasks, two seeds, four registered arms,
and therefore **24 scored trajectories**. CoProMem learns on evaluation tasks;
there is no validation freeze or pre-injection replay.

## 1. Select inputs before running

Choose three distinct AppWorld task IDs, in this order:

| Task | Initial descriptor compatibility | Purpose |
| --- | --- | --- |
| A | `unknown` | Learn a new structurally grounded schema from a successful trial. |
| B | `unknown`, with the same structural signature as A | Test whether the task-boundary winner from A is available on B. |
| C | `compatible` | Test retrieval from the scored train warm start. |

Use only the public task instruction and API shape to write descriptors. Include
ordered `operation`, `input_slots`, and `output_slots`; exclude concrete values,
post-execution checks, and private scorer data. A and B need different task IDs
and the same exact signature. The acquisition export must contain scored,
public **train** histories with no task ID shared with A, B, or C. It must carry
`acquisition_identity` (`task::seed=N::trajectory=N`), `task_id`, `instruction`,
`history`, `history_sha256`, `source_artifact_sha256`, and `after_score` for each
trajectory. `history_sha256` uses the canonical JSON digest in
`copromem.experiments.reme_copromem.runner.digest`; keep raw export and all run
artifacts local.

The following is a shape example, **not a ready-to-run manifest**. Replace the
task IDs, public operations/slots, acquisition count/hash, and cost limits after
estimating the worst-case provider exposure. Set `fits_hard_cap` to `true` only
after that estimate fits the chosen cap. The two trial IDs and seeds must be
distinct; the runner executes each arm with up to 30 actions per trajectory.

```json
{
  "protocol": "continuous_copromem_v5",
  "arms": ["no_memory", "official_upstream_reme_fixed", "official_upstream_reme_dynamic", "copromem_dynamic"],
  "acquisition": {
    "expected_trajectories": 0,
    "source_export_sha256": "REPLACE_WITH_SHA256"
  },
  "evaluation": {
    "task_ids": ["TASK_A", "TASK_B", "TASK_C"],
    "trial_ids": [0, 1],
    "seeds": [101, 102],
    "expected_trajectories": 24,
    "descriptors": {
      "TASK_A": [{"operation": "REPLACE_API", "input_slots": ["input"], "output_slots": ["output"]}],
      "TASK_B": [{"operation": "REPLACE_API", "input_slots": ["input"], "output_slots": ["output"]}],
      "TASK_C": [{"operation": "REPLACE_KNOWN_API", "input_slots": ["input"], "output_slots": ["output"]}]
    },
    "expected_initial_compatibility": {
      "TASK_A": "unknown",
      "TASK_B": "unknown",
      "TASK_C": "compatible"
    }
  },
  "budget": {
    "fits_hard_cap": false,
    "hard_cap_usd": 0,
    "ledger_dispatch_cap_usd": 0,
    "historical_charged_or_reserved_usd": 0,
    "copromem_decomposition_calls": 0
  }
}
```

The full source commit must be fixed before preparation. The runner refuses
tracked `src/` or `scripts/` changes after freezing. Use a fresh run directory;
v4 or earlier v5 bank states cannot enter this version 5 state format.

## 2. Prepare and freeze

From the repository root, use `.venv/bin/python` with `PYTHONPATH` set (or
replace it with another project Python that has the same dependencies). The
four external runtime paths must point to
the pinned upstream ReMe checkout/environment and native AppWorld
checkout/environment. The OpenRouter key is read from the local ignored `.env`
file by the runner and ReMe service; do not put it in the manifest or logs.

```bash
export PYTHONPATH="$PWD/src:$PWD"
export COPROMEM_ROOT="$PWD"
export COPROMEM_RUN_DIR="$PWD/artifacts/pilot-v5-001"
export COPROMEM_ACQUISITION_POOL="/absolute/path/to/scored-train-acquisition.json"
export COPROMEM_REME_SOURCE="/absolute/path/to/reme-source"
export COPROMEM_REME_PYTHON="/absolute/path/to/reme-python"
export COPROMEM_APPWORLD_ROOT="/absolute/path/to/appworld-source"
export COPROMEM_APPWORLD_PYTHON="/absolute/path/to/appworld-python"

.venv/bin/python -m pytest -q
.venv/bin/python -m copromem.experiments.reme_copromem.prepare_v5 \
  --template /absolute/path/to/pilot-template.json \
  --acquisition "$COPROMEM_ACQUISITION_POOL" \
  --run "$COPROMEM_RUN_DIR"

.venv/bin/python -m copromem.experiments.reme_copromem.freeze_v5 \
  --template /absolute/path/to/pilot-template.json \
  --acquisition "$COPROMEM_ACQUISITION_POOL" \
  --run "$COPROMEM_RUN_DIR" \
  --dependency-file /absolute/path/to/pinned-upstream-agent-file.py \
  --dependency-file /absolute/path/to/pinned-appworld-scorer-file.py

.venv/bin/python -m copromem.experiments.reme_copromem.config --preflight
```

Pin actual dependency files used by the run, not the placeholder paths above.
`prepare_v5` checks acquisition identities, history hashes, and disjoint task
IDs. `freeze_v5` records the source commit, bank/export/gate hashes, and
dependency hashes. Preflight requires at least 5 GiB free and writes
`copromem/descriptor-audit.json`. Inspect that file before any paid evaluation:
it must report A=`unknown`, B=`unknown`, C=`compatible`. A mismatch is a
descriptor/input problem to fix in a **new** run directory before running.
Do not edit a frozen manifest or bank in place.

## 3. Run and monitor

```bash
.venv/bin/python -m copromem.experiments.reme_copromem.config
```

Watch `runner-status.json`, `live-summary.json`, `progress.jsonl`, and
`ledger.jsonl` under `COPROMEM_RUN_DIR`. The four arm counts must reach six
each. The ledger's charged plus reserved exposure must remain below the
manifest dispatch cap. If the runner fails closed on an unsettled reservation,
hash mismatch, or uncertain ReMe update, preserve the run directory for audit;
do not delete a marker, ledger entry, or scored artifact to force a resume.

After A finishes, check its `copromem/task_updates/TASK_A.json` marker.
`winner_episode_id` must identify a fully successful, structurally grounded
trial to exercise positive learning. If it is `null`, the pilot is **inconclusive
for cross-task learning**: retain the result and plan a new pilot with a task
more likely to succeed. A task can be scored successfully yet remain pending
if the public history lacks observable structure; that does not satisfy this
criterion.

## 4. Restart drill

The current runner has no deterministic `--stop-after-task` switch. For a
separate restart drill, wait until A's task update marker exists, then send
`SIGINT` to the foreground runner (Ctrl-C), let its ReMe services close, and
start the **same command with the same frozen manifest and run directory**.
Because the runner may already have started B, this also tests recovery from
partial B artifacts. Do not use `SIGKILL`; an in-flight reserved call can
correctly prevent automatic resume. Keep the uninterrupted pilot's results
separate from this drill if comparing scores.

For the restart drill, record hashes of A's scored artifacts and task state
before and after resume. They must be unchanged, and A's episode count must
not increase. The B pre-state hash must equal A's post-state hash. If the
interrupt lands during an external side effect and resume fails closed, record
the failure as an engineering finding; do not label it an idempotent pass.

## 5. Acceptance checks

The pilot passes its **engineering** checks only when all of the following
hold:

1. `final-report.json` says `completion.complete=true` and `24/24`; each arm
   has six scored artifacts, CoProMem has six retrieval records, and there are
   three task update markers.
2. For each task, both CoProMem retrieval records have the same
   `provenance.pre_state_sha256` as that task's pre-state. Each task's next
   pre-state equals its previous task's post-state. The two trials of a task do
   not observe each other's updates.
3. A has a winner. Its `episode_schemas[winner_episode_id]` in A's task state
   names a provisional schema; B's retrieval records select that schema and
   list only procedures for its supported steps. C retrieves its compatible
   warm-start schema. Candidate/quarantined schemas never enter guidance.
4. The winner is the eligible full-success trial with best score, then lowest
   settled cost, action count, and trial ID. Every trial is recorded once; only
   the winner is promoted. Failed tasks add no positive procedure.
5. The restart drill, if performed, preserves completed artifact/state hashes
   and does not repeat the task-boundary merge. No provider reservation remains
   unsettled at successful completion.

Inspect `retrieval/copromem_dynamic/<task>/trial-<id>.json`,
`copromem/task_pre_states/`, `copromem/task_states/`,
`copromem/task_updates/`, and `final-report.json` for these checks. Keep raw
histories, scores, ledgers, and provider responses in the ignored local run
directory. A 24-trajectory pilot supports operational confidence only; larger
preregistered evaluation is needed for performance claims.
