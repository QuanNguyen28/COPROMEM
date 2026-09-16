# Cycle 1 decision: KEEP the shared-checkpoint protocol

Date: 2026-09-16. Branch `codex/copromem-research-loop`; base commit `1802510`;
uncommitted implementation identified by the source hashes in the raw report.

## Change and checks

Added immutable content-addressed checkpoints, a write-once request/response store,
matched stage/replicate seeds, six shared-handoff arms, task-level paired reporting,
failure isolation, split leakage checks, resumable requests, and a persistent budget
reservation ledger. All 29 tests passed before the real pilot; Ruff/formatting cleanup
also preserved the 12 original tests (two fixtures were made disjoint to remove leakage).

## Real diagnostic result

- Config: `research/configs/cycle01_paired.json`.
- Model/provider: `mistralai/ministral-3b-2512`, `mistral`, fallback disabled.
- Dataset: 3 build + 4 development tasks selected by hash from GSM8K **train**.
- Repeats: 2 per development task; 8 paired rows, only 4 independent task clusters.
- Physical requests: 54; logical references: 70; cached reuses: 16.
- Reported API cost: **USD 0.00152572**, below the USD 0.25 pilot cap.
- Recorded provider failures: 0. All 54 responses had finish reason `stop`.
- Raw report: `artifacts/research/cycle01_paired/reports/bcf80cce84fffe43dc05c3e97016e610bdb753705db7a3df0810d92b499f5ad3.json`.
- Raw prompts, responses, provider IDs, checkpoints, outcome rows, dataset selection,
  budget reservations/settlements, and source hashes are in adjacent subdirectories.

| Arm | Correct / 8 | Recovery | Interpretation |
|---|---:|---|---|
| No memory | 8 | None | Pilot ceiling; not a representative accuracy estimate |
| Success-only memory | 8 | None | No observed benefit |
| Textual schema rule | 8 | None | No observed benefit |
| Sham retry | 7 | Schema-triggered | One harmful flip, zero beneficial flips |
| Static verifier | 7 | Schema-triggered | One harmful flip, zero beneficial flips |
| Historical CoProMem schema | 8 | Not admitted | Identical to no memory; no learned intervention |

The schema arm's nominal +1 versus static is **not a learning win**: its bank was empty.
It simply avoided static verification's harmful recovery. All three build tasks were
solved correctly, although only one build plan passed the schema verifier.

## Individual harmful flips

- Static: `train-6861`, repeat 1, changed correct 24 to 12.
  Checkpoint `b1d3451ab6060252fa2acc1fa6ffca7f67cb9bbb1dc036d60c5e608c3c4c3afb`.
- Sham: `train-7226`, repeat 0, changed correct 107 to 103.
  Checkpoint `bd3111fca49c4c28142473b972b6262c4ba62bf9467a74d4b3b9ec7b6dd80dd2`.
- Each arm's success delta versus no memory is -0.125; task-cluster bootstrap interval
  [-0.375, 0]. With four clusters this interval is descriptive and does not establish harm
  frequency in the population.

## Hostile-review critique

The unchanged schema is a poor proxy for downstream correctness. Changing a correct
solver input can introduce an error. Differing recovery outputs and downstream stochastic
responses remain alternative explanations for each individual flip; matching checkpoints
does not assign the error to a particular textual clause. Additional calls and context
length differ and are reported, even though caps are shared. Neither efficacy nor novelty
passes from these eight rows.

## Decision and next experiment

**KEEP** the protocol and instrumentation. Do not promote the current method or scale
final testing. Next, test generic evidence-based predicate induction and admission using
same-task contrasts and independent benign boundary cases. Retain null/empty-bank outcomes.
