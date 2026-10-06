# ALFWorld pilot table

All rows use the same OpenRouter action model. Results and code in this
directory are external to the CoProMem repository.

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
