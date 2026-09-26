# Acquisition-only readiness report

Decision: **NO-GO** for a corrected evaluation smoke and for the USD 35 efficacy
pilot. The preregistered threshold—two official 2/2 source episodes across the
two distinct tasks—was not reached. No evaluation task or evaluation arm was
opened or dispatched.

## Failure diagnosis and permitted interface change

The public action traces showed repeated generic interface mistakes: imports,
reflection (`dir`/`inspect`/`hasattr`), guessed API names, and prolonged API
enumeration rather than use of the prebound `apis` object and documented API
route. The official scorer exposed only aggregate `pass_count=1, fail_count=1`
for each episode, not the name or implementation of the failed hidden check.
No hidden checker, state, or task-specific solution was inspected.

The new manifest therefore added one common executor-interface contract: use
only prebound `apis` and documented API names; do not import, reflect, or guess
endpoints; inspect the task then documentation only as needed and execute within
the action budget. It was identical for every task and seed. It did not improve
official success.

## Frozen trajectory results

| Task | Seed | Official score | Calls | Prompt / completion tokens | Valid tools | Latency | USD |
|---|---:|---:|---:|---:|---:|---:|---:|
| `50e1ac9_1` | 101 | 1 / 2 | 8 | 44,700 / 598 | 7 / 8 | 10.773 s | 0.0141276 |
| `50e1ac9_2` | 101 | 1 / 2 | 3 | 6,279 / 233 | 2 / 3 | 3.504 s | 0.0021633 |
| `50e1ac9_1` | 202 | 1 / 2 | 10 | 40,958 / 721 | 10 / 10 | 11.618 s | 0.0131526 |
| `50e1ac9_2` | 202 | 1 / 2 | 2 | 4,767 / 189 | 1 / 2 | 2.839 s | 0.0016569 |
| `50e1ac9_1` | 303 | 1 / 2 | 1 | 633 / 128 | 0 / 1 | 1.249 s | 0.0003435 |
| `50e1ac9_2` | 303 | 1 / 2 | 2 | 4,767 / 189 | 1 / 2 | 3.570 s | 0.0016569 |
| **Total** | — | **0 / 6 successes** | **26** | **102,104 / 2,058** | **21 / 26** | **33.553 s** | **0.0331008** |

All six trajectory starts, action plans, native action records, official scores,
and provenance records are write-once. Five trajectories have action-bearing
trace hashes. The zero-action trajectory (`50e1ac9_1`, seed 303) ended in a
128-token truncation before a native action; its immutable empty trace was
reconciled from the start journal as
`a878ece0a17b5884edded17e917d42911458697c10c5c9d54405d03e8ea2b6b9`.
The gate still rejects zero-action evidence.

## Budget and lifecycle

The new append-only ledger carried all 76 earlier records and USD 0.07770738.
It recorded and settled all 26 readiness calls, for all-in exposure of
**USD 0.11080818 / USD 1.00**. No unregistered retry, fallback, background
call, memory placeholder, or evaluation call occurred.

Because no successful shared source pool exists, ReMe fixed, ReMe dynamic, and
CoProMem v2 memory construction/lifecycle validation were not run. Creating
memory anyway would violate the no-generic/no-authored-memory gate. ReMe remains
a faithful adaptation, not direct upstream reproduction.
