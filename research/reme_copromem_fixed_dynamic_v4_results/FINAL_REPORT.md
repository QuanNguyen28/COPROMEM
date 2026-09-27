# fixed_dynamic_v4 final report

**Exploratory analysis of a completed fixed-dynamic experiment.**

| Arm | Completed | Successes | AvgScore | SuccessRate | AvgActions |
|---|---:|---:|---:|---:|---:|
| copromem_dynamic | 64 | 48 | 0.859 | 0.750 | 15.9 |
| copromem_fixed | 64 | 43 | 0.847 | 0.672 | 17.8 |
| no_memory | 64 | 49 | 0.875 | 0.766 | 17.3 |
| official_upstream_reme_dynamic | 64 | 42 | 0.799 | 0.656 | 16.7 |
| official_upstream_reme_fixed | 64 | 50 | 0.874 | 0.781 | 17.8 |

All 320/320 registered trajectories completed. A success is an official AppWorld score of 1.0; AvgScore retains fractional official scores.

## Paired exploratory analysis

Every arm pair has 64 matched task/seed/trial records. Confidence intervals are task-cluster bootstrap 95% intervals; p-values are exact task-level sign-flip tests with Holm correction.

| Pair (left - right) | Score difference [95% CI] | score dz / Holm p | Success difference [95% CI] | success dz / Holm p |
|---|---:|---:|---:|---:|
| copromem_dynamic__minus__copromem_fixed | 0.0122 [-0.0811, 0.0939] | 0.066 / 1.0000 | 0.0781 [-0.0469, 0.2031] | 0.290 / 1.0000 |
| copromem_dynamic__minus__no_memory | -0.0158 [-0.0991, 0.0770] | -0.085 / 1.0000 | -0.0156 [-0.0938, 0.0781] | -0.092 / 1.0000 |
| copromem_dynamic__minus__official_upstream_reme_dynamic | 0.0605 [0.0175, 0.1112] | 0.613 / 0.1953 | 0.0938 [0.0156, 0.1875] | 0.522 / 1.0000 |
| copromem_dynamic__minus__official_upstream_reme_fixed | -0.0145 [-0.1504, 0.1131] | -0.052 / 1.0000 | -0.0312 [-0.1875, 0.1250] | -0.095 / 1.0000 |
| copromem_fixed__minus__no_memory | -0.0280 [-0.1227, 0.0736] | -0.137 / 1.0000 | -0.0938 [-0.2500, 0.0625] | -0.286 / 1.0000 |
| copromem_fixed__minus__official_upstream_reme_dynamic | 0.0483 [-0.0326, 0.1440] | 0.259 / 1.0000 | 0.0156 [-0.1250, 0.1719] | 0.048 / 1.0000 |
| copromem_fixed__minus__official_upstream_reme_fixed | -0.0267 [-0.1059, 0.0544] | -0.157 / 1.0000 | -0.1094 [-0.2344, 0.0156] | -0.424 / 1.0000 |
| no_memory__minus__official_upstream_reme_dynamic | 0.0763 [-0.0283, 0.1722] | 0.366 / 1.0000 | 0.1094 [-0.0156, 0.2344] | 0.400 / 1.0000 |
| no_memory__minus__official_upstream_reme_fixed | 0.0013 [-0.0937, 0.1175] | 0.006 / 1.0000 | -0.0156 [-0.1719, 0.1406] | -0.047 / 1.0000 |
| official_upstream_reme_dynamic__minus__official_upstream_reme_fixed | -0.0750 [-0.2026, 0.0353] | -0.296 / 1.0000 | -0.1250 [-0.2812, 0.0156] | -0.395 / 1.0000 |

## Action analysis

All-trajectory action means and success-conditioned action means are reported separately; conditioning changes the population and is not an efficacy estimate.

| Arm | all trajectories | successful trajectories (n) | successful-only mean actions |
|---|---:|---:|---:|
| copromem_dynamic | 15.92 | 48 | 13.77 |
| copromem_fixed | 17.78 | 43 | 14.02 |
| no_memory | 17.33 | 49 | 14.18 |
| official_upstream_reme_dynamic | 16.69 | 42 | 14.60 |
| official_upstream_reme_fixed | 17.75 | 50 | 16.22 |

Pairwise all-trajectory and both-successes-conditioned action differences, with their pair denominators, are in `statistical-analysis.json`; no action-only comparison is treated as evidence of efficacy.

## Conclusions

- ReMe Fixed had the largest number of full successes.
- No Memory had the highest mean score, approximately tied with ReMe Fixed.
- CoProMem Dynamic improved over CoProMem Fixed and used the fewest mean actions.
- CoProMem Dynamic did not outperform No Memory or ReMe Fixed on raw efficacy.
- ReMe Dynamic underperformed ReMe Fixed in this run.
- No superiority claim is made: corrected paired exploratory tests govern any inferential interpretation.

## Limitations

- This is an exploratory faithful adaptation, not an exact ReMe paper reproduction.
- Results are exact-ID holdout only; they do not establish task-family or benchmark-wide generalization.
- Raw trajectories, prompts, memory text, provider responses, and local evidence remain excluded from Git.
