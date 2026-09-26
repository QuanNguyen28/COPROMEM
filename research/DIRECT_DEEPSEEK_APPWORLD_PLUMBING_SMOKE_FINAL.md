# Immutable plumbing-smoke record

Status: **completed plumbing validation; invalid for method comparison**.

The run used the official direct DeepSeek Chat Completions route, model
`deepseek-flash`, `reasoning_effort: none`, native function calling, the
persistent WSL AppWorld worker, the native AppWorld scorer, and the immutable
successor ledger.  It was an exposed-task plumbing test only.

## Immutable accounting

* Carried attempts: 10; new attempts: 46; total: **56 / 88**.
* Every new reservation has a settlement: **46 / 46**.
* Carried exposure: USD 0.03131748; new settled exposure: USD 0.03285030;
  all-in charged-or-reserved exposure: **USD 0.06416778 / USD 1.00**.
* The redacted result artifact SHA-256 is
  `EA45E3187B6CB1166DD35C8E1A2DD1F42967E06AEA62ABFD5D677D6008DCEB8C`.

## Official scorer observations

`50e1ac9_2` and every evaluation arm on `fac291d_1` returned an official
**1/2** score.  `50e1ac9_1` has two settled dispatches but no persisted native
action or scorer artifact and is therefore recorded as a failed, non-replayed
acquisition.  These are observations, not rankings or efficacy estimates.

| Stream | Calls | Prompt / completion tokens | Valid tools | Settled USD |
|---|---:|---:|---:|---:|
| Acquisition `50e1ac9_2` | 10 | 14,346 / 594 | 10 / 10 | 0.0050166 |
| No Memory | 10 | 34,809 / 740 | 10 / 10 | 0.0113307 |
| ReMe fixed faithful adaptation | 4 | 3,705 / 321 | 3 / 4 | 0.0014967 |
| ReMe dynamic faithful adaptation | 10 | 14,100 / 605 | 9 / 10 | 0.0049560 |
| CoProMem v2 | 10 | 29,515 / 595 | 10 / 10 | 0.0095685 |

The two `50e1ac9_1` calls cost USD 0.0004818; their response token, latency,
and tool-validity telemetry was not persisted by the early runner.

## Fidelity limitations and root cause

The original runner held action rows only in memory and wrote `smoke_result`
only after all trajectories.  The controller observation window ended while
the process was live; the initial task therefore retained settled requests but
lost its volatile worker/action/scorer state.  This is a persistence defect,
not evidence of an AppWorld or provider failure.

Further, failed acquisition resulted in a generic failure suffix being supplied
to the two memory arms.  That is not method-specific ReMe or CoProMem memory.
ReMe was a **faithful lifecycle adaptation**, not direct execution of the
pinned upstream implementation.  The raw output artifact was sanitized after
it was found to contain task-private native output; only redacted execution
metadata remains.

Consequently this record demonstrates direct transport, native tool execution,
stateful worker/scorer operation, and ledger mechanics only.  It supports no
claim about efficacy, ranking, superiority, transfer, or generalization.
