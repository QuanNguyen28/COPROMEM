# AppWorld development-only pilot: hard paid-call and cost ceiling

## Fixed caps and pricing assumptions

Use only direct DeepSeek `deepseek-flash` in non-thinking mode, with no
fallback.  This estimate uses the published **peak** uncached rates: $0.30/M
input and $1.20/M output.  Enforce executor input <=6,000 tokens and output
<=1,000 tokens per completion; enforce summarizer input <=12,000 and output
<=2,000.  If the route price or requested token cap is higher, stop before the
call.

| Role | Calls | Input cap | Output cap | Input tokens | Output tokens | USD ceiling |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Executor, acquisition | 6 x 8 x 30 = 1,440 | 6,000 | 1,000 | 8.640M | 1.440M | $4.320 |
| Executor, evaluation | 8 x 4 arms x 4 trials x 30 = 3,840 | 6,000 | 1,000 | 23.040M | 3.840M | $11.520 |
| ReMe distillation / validation / reflection | 144 | 12,000 | 2,000 | 1.728M | 0.288M | $0.864 |
| Official AppWorld scorer | 0 model calls | — | — | 0 | 0 | $0.000 |
| CoProMem LLM decomposition | 320 | 12,000 | 2,000 | 3.840M | 0.640M | $1.920 |
| **Total** | **5,744** | | | **37.248M** | **6.208M** | **$18.624** |

The 144 summarizer cap covers at most 48 trajectory distillations, 18 failure
reflections (three per acquisition task), six comparative summaries, and 72
validation/deduplication operations.  ReMe fixed/dynamic share these acquired
summaries; they must not redistill the raw pool. CoProMem does **not** force
the offline fallback: with a configured API key, native recursive decomposition
is used and globally capped at 320 calls across 48 acquisition and 32
evaluation retrievals. Any method-specific paid call not listed here is
prohibited.

The hard authorization request is **$20 USD**, leaving $1.376 only for
provider billing rounding.  No retry, judge, embedding, fallback, or hidden
background call is permitted beyond the table.  This is below the requested
$30 ceiling.

## Approval required

Budget for the present stage remains **$0**.  Do not invoke this pilot until
the user explicitly approves the $20 hard cap and the frozen AppWorld
development manifest, provider preflight, dependency lock, and scorer smoke
test have been reviewed.
