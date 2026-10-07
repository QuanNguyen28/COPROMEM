# ALFWorld pilot and final results

All rows use the same OpenRouter action model. Raw episodes and detailed logs
are stored under the ignored `benchmarks/results/` directory.

| Run | Steps | Arm | Tasks | Success | Rate | Avg steps | Retrieval hits | Action-model cost |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| `20261001T165132Z` | 30 | no memory | 6 | 4 | 66.7% | 16.5 | 0 | included in run total |
| `20261001T165132Z` | 30 | CoProMem v2 | 6 | 4 | 66.7% | 16.0 | 2 | included in run total |
| `20261001T171427Z` | 60 | no memory | 2 | 1 | 50.0% | 47.0 | 0 | included in run total |
| `20261001T171427Z` | 60 | CoProMem v2 | 2 | 1 | 50.0% | 37.5 | 0 | included in run total |
| `20261001T181554Z` | 60 | no memory | 2 | 0 | 0.0% | 60.0 | 0 | 0.035460 cumulative |
| `20261001T181554Z` | 60 | CoProMem v2 | 2 | 1 | 50.0% | 48.0 | 0 | 0.057973 cumulative |
| `20261001T181554Z` | 60 | pinned legacy REmE | 2 | 0 | 0.0% | 60.0 | 0 | 0.090005 cumulative |

The latest run used pinned legacy REmE commit
`2f37a159b72a04ac1885a7db7f1a663a833e7791`. Its service retrieved zero
memories for both tasks. It attempted trajectory summarization after each
episode, but the legacy failure extractor returned no parseable memory, so no
experience was available for the second task. The service-side model usage is
not included in the action-model cost column.

## Final sorted tasks 1–100

Each arm completed all 100 tasks with a 60-step per-task cap. Average steps
are computed with episode lengths capped at 60. Cost uses the specified rates
of $0.0152 per 1M input tokens and $1.28 per 1M output tokens; auxiliary
memory-service calls are included only when their token usage was recorded.

| Arm | Completed | Successes | Success rate | Average steps | Estimated cost (USD) |
|---|---:|---:|---:|---:|---:|
| No memory | 100/100 | 82 | 82.0% | 23.12 | $1.2700 |
| CoProMem | 100/100 | 91 | 91.0% | 20.91 | $1.1722 |
| ReMe | 100/100 | 82 | 82.0% | 25.09 | $1.3334 |
| ReasoningBank | 100/100 | 85 | 85.0% | 19.06 | $0.9056 |
