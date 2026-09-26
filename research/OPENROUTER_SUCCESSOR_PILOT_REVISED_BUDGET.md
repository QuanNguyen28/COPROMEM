# Revised OpenRouter successor pilot - conservative budget registration

## Design fixed before payload access

- Acquisition: 12 scenarios x 4 shared trajectories x 30 actions = 1,440
  executor calls.
- Evaluation: 32 tasks x 2 seeds x 4 arms x 30 actions = 7,680 executor
  calls.
- Every executor call is bounded by 6,144 input and 1,024 completion tokens.
- ReMe fixed and dynamic faithful adaptations are deterministic local lifecycle
  code, so they register zero paid lifecycle calls.
- CoProMem v2 retains native API-key decomposition, with the adapter's existing
  global, fail-closed cap of 320 LLM decomposition calls.  The common 1,024
  completion-token ceiling is used for their conservative accounting as well.
- Price ceilings: USD 0.30 / million input and USD 1.20 / million completion.

## Worst-case ledger

| Component | Calls | Per-call cap | Conservative USD |
| --- | ---: | ---: | ---: |
| Shared acquisition executor | 1,440 | 0.0030720 | 4.4236800 |
| Evaluation executor | 7,680 | 0.0030720 | 23.5929600 |
| CoProMem decomposition | 320 | 0.0030720 | 0.9830400 |
| Prior OpenRouter failed canary (retained) | 1 | fixed | 0.0100000 |
| Corrected OpenRouter canary (settled) | 1 | actual | 0.0000651 |
| 15% non-dispatchable price/serialization contingency | - | - | 4.3499520 |
| **All-inclusive maximum** | **9,442 paid attempts** | - | **33.3596971** |

The 15% margin is not callable budget: no retry, fallback, judge, background,
or unregistered request may consume it. The USD 35 hard cap retains USD
1.6403029 unused headroom. The predecessor direct-DeepSeek and older
OpenRouter development ledgers are deliberately excluded from pilot efficacy
estimates and this successor ledger; only the two route-canary records are
carried forward.

The 320-call CoProMem cap is a genuine fail-closed algorithm limit: exhaustion
is a protocol/runtime failure, never permission to silently switch to the
offline decomposition fallback.
