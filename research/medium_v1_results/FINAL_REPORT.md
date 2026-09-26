# medium_v1 final report

**Diagnostic faithful adaptation; not an exact ReMe reproduction.**

Manifest SHA-256: `486af47a648baaeae7ca83e6870b5001564afe06d41ce6d6e963305b63089eb9`

Completion: **640 / 640** evaluation trajectories. Hard cap: **USD 140**; charged/retained: **USD 1.743165**.

## Arm metrics

| Arm | Avg@4 | Pass@4 | trajectories | mean actions |
|---|---:|---:|---:|---:|
| no_memory | 0.8209 | 0.8000 | 160 | 19.26 |
| official_upstream_reme_fixed | 0.8040 | 0.8500 | 160 | 19.21 |
| official_upstream_reme_dynamic | 0.8638 | 0.8500 | 160 | 19.51 |
| copromem_v2 | 0.8377 | 0.8250 | 160 | 19.61 |

## Paired task-level CoProMem comparisons

| Comparator | tasks | mean difference | 95% normal CI | W/L/T |
|---|---:|---:|---:|---:|
| no_memory | 40 | 0.0168 | [-0.0220, 0.0555] | 15/7/18 |
| official_upstream_reme_fixed | 40 | 0.0337 | [-0.0125, 0.0798] | 16/7/17 |
| official_upstream_reme_dynamic | 40 | -0.0261 | [-0.0621, 0.0099] | 8/12/20 |

## Scientific limitation

ReMe retrieval was empty; CoProMem evaluation supplied empty intent and consequently generic/empty guidance. This is diagnostic plumbing evidence, not a valid memory-method efficacy comparison.

**REVISE:** no superiority claim is supported.
