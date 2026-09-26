# ReMe–CoProMem conservative cost estimate

## Price and route preflight

The official DeepSeek API currently documents `deepseek-flash` as
DeepSeek-V4.1-Flash, non-thinking capable, with a 1M-token context limit.
Published peak prices are USD $0.30/M uncached input and $1.20/M output;
off-peak prices are half.  The public documentation does not expose an
immutable model-revision identifier for this route.  It is therefore available
but not yet sufficiently pinned for a final run: record the provider response
metadata and pricing snapshot immediately before a run, and stop if the route
or non-thinking flag cannot be verified.  No fallback is authorized.

## Superseded full-study bound

The original bound below is retained for auditability.  It incorrectly sampled
the same no-memory acquisition experience separately for each memory arm.  See
`REME_COPROMEM_CALL_AUDIT.md` for the corrected 787,680 executor-call bound
and `REME_COPROMEM_PILOT_COST_ESTIMATE.md` for the present $20 pilot cap.

| Component | Maximum executor calls |
| --- | ---: |
| BFCL acquisition: 50 x 8 x 5 x 30 x 3 | 180,000 |
| BFCL evaluation: 150 x 4 x 6 x 30 x 3 | 324,000 |
| AppWorld acquisition: 90 x 8 x 5 x 30 x 3 | 324,000 |
| AppWorld evaluation: 168 x 4 x 6 x 30 x 3 | 362,880 |
| **Total** | **1,190,880** |

This is an upper bound, not a forecast: early termination reduces it; retries,
failure reflections, summarization, judging, and tool-provider fees increase
it.  An exact estimate requires the frozen prompts and a zero-cost trace of
actual per-step token lengths.

## Conservative USD envelope

At peak published rates, an executor call with 2.5k–8k uncached input and
0.5k–1.5k output costs about $0.00135–$0.00420.  The executor-only ceiling is
therefore approximately **$1,608–$5,002**.  Add 20% for acquisition
distillation/reflections, judge calls, retries, and unexpected context growth:
**$1,930–$6,003**.  Off-peak token prices halve the token portion, but this
estimate intentionally does not rely on off-peak availability or prompt-cache
hits.

This excludes storage, egress, compute for local services, benchmark hosting,
and any paid tool/API operations.  Those must be priced or bounded during
environment preflight.  A prudent hard cap for a full run is therefore not
inferable from the brief; it requires explicit user approval of a selected cap
within this envelope.

## Required ledger fields

Every request and tool operation must record timestamp, arm, benchmark, seed,
task ID, trial, phase (acquisition/evaluation), provider/model route, input and
output tokens, cache tokens, USD amount, latency, retries, tool calls, and
error class.  The ledger must never be overwritten; resumed runs append with a
new run ID.

## Gate decision

**STOP — no explicit budget is configured.**  Do not make paid calls until the
user supplies an approved maximum USD amount and accepts the frozen provider
route, environment/split hashes, and revised estimate.
