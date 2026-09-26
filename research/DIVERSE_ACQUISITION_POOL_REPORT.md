# Diverse acquisition-only readiness run - immutable report

**Decision: NO-GO for a corrected evaluation smoke.** This was an acquisition-only, exposed-development run. No evaluation task or evaluation arm was started, and this report makes no efficacy, superiority, transfer, or generalization claim.

## Frozen protocol

- CoProMem source: `6eca54ca14a7935fcdcdc1a9a77319ed113a0679`.
- Executor transport: official direct DeepSeek Chat Completions; `deepseek-flash`; non-thinking; native tool calling; no fallback or model substitution.
- Twelve development task IDs were selected and frozen *before their payloads were opened*: `530b157_1`, `4ec8de5_1`, `b119b1f_1`, `d4e9306_1`, `0d8a4ee_1`, `37a8675_1`, `3ab5b8b_1`, `df61dc5_1`, `383cbac_1`, `23cf851_1`, `57c3486_1`, and `68ee2c9_1`.
- One preregistered trajectory per task, seed 701, with at most 30 native actions. The base prompt, tools, runtime, and limits were uniform.
- The prior zero-cost audit identified two provider-neutral tool-call truncations at the 256 completion-token ceiling. The ceiling was consequently frozen uniformly at 1024 for every trajectory; no prompt or task-specific change was made.
- The complete pool—including success and failure episodes—was retained. No trajectories were replaced based on outcome.

The frozen manifest SHA-256 is `5cdf106f53a21e69f5043194dccaa258e6960b4b4895788dfcec4b5052f1bb7c`; the frozen development inventory hash recorded there is `9fa976589300ea8905708257144d801d1604b06d85fb0181e381df8a3ba85001`.

## Predeclared decision rule

GO required at least three official 2/2 successful episodes spanning at least three task-family prefixes, plus valid provenance-bound outputs from all three memory lifecycles. Anything else is NO-GO, without evaluation.

## Official acquisition outcomes

| Task | Official result | Outcome |
| --- | ---: | --- |
| `530b157_1` | 7/10 | failure |
| `4ec8de5_1` | 2/2 | success |
| `b119b1f_1` | 0/6 | failure |
| `d4e9306_1` | 5/6 | failure |
| `0d8a4ee_1` | 4/5 | failure |
| `37a8675_1` | 0/6 | failure |
| `3ab5b8b_1` | 2/6 | failure |
| `df61dc5_1` | 2/7 | failure |
| `383cbac_1` | 2/2 | success |
| `23cf851_1` | 1/2 | failure |
| `57c3486_1` | 1/5 | failure |
| `68ee2c9_1` | 4/5 | failure |

There were two successes in two families (`4ec8de5`, `383cbac`), below the preregistered 3-success/3-family threshold. This is an executor/acquisition-signal NO-GO, not a comparison result.

## Lifecycle processing

All three methods processed the same frozen complete pool. ReMe remains labeled **faithful adaptation**, not direct paper-era upstream reproduction.

| Method | Provenance label | Memory SHA-256 | Empty |
| --- | --- | --- | --- |
| ReMe fixed faithful adaptation | `reme-faithful-adapter-fixed` | `a833ff464b2be3ad2fafe5d5173db69c48d1a81e5371386f42592ada0f56e7ea` | no |
| ReMe dynamic faithful adaptation | `reme-faithful-adapter-dynamic` | `405ceb7cb20df0d8a64e06979b9ce7c67e0de3fedd8502508389cedaa7975948` | no |
| CoProMem v2 | `copromem-v2` | `4402a9a842aa20546efeb2187f3c240ce454cf07d5bc687de6b49f0cb9772a89` | no |

The outputs are provenance-bound, non-empty, and pairwise distinct. No generic placeholder was supplied as memory. They are not used for an evaluation in this run.

## Budget ledger and execution accounting

- Pre-run immutable history: 123 attempts and USD 0.13762998 exposure.
- New acquisition ledger: 300 registered reservations, 299 settled calls, and one retained unsettled reservation. The retained reservation has no response telemetry and remains charged/reserved by design.
- Current all-inclusive ledger exposure: **USD 0.71597348**.
- Acquisition-only ceiling: USD 8.00; overall approved study ceiling: USD 35.00. Neither was exceeded.
- The new pool used 299 settled direct-model calls. Per-task request counts ranged from 13 to 30, respecting the 30-action ceiling. Native tool validity was recorded for every settled tool response.

## Integrity and deviations

Each action was journaled before subsequent dispatch; traces, official scores, and trajectory hashes were frozen. An interrupted `b119b1f_1` trajectory was recovered by replaying only its already-journaled native actions into a fresh worker, with **zero model replay**, then officially scored.

The initial process was stopped after an unrelated C-drive-space safety breach. A per-trajectory C-space guard was added before resumption. At final verification, C: had 7.13 GB free, below the 10 GB threshold; therefore no further acquisition or evaluation is permitted without storage remediation. Raw action journals are restricted local research artifacts and must not be published or moved as general artifacts because action text can contain task-private runtime values.

The result SHA-256 is `c3a197b9af27b3edb994d4b4e0ed78343192e8f6b47f3682253f9230e87d2bcb`.

## Verification

After completion, the focused deterministic suite passed: 16 tests covering transport truncation handling, acquisition journaling/gating, append-only ledger behavior, comparison adapters, and live-worker fixture paths. No paid calls occurred during this verification.

## Required next step

Do not run the evaluation smoke or efficacy pilot from this pool. Before a new study, remediate C-drive pressure, retain the append-only artifacts, and choose an acquisition source/executor/benchmark design capable of meeting a prospectively fixed diversity-success threshold.
