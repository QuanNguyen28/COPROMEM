# OpenRouter successor pilot - pre-dispatch budget gate

**Decision: blocked fail-closed. No fresh task payload, acquisition, lifecycle,
or evaluation request was dispatched.**

## Fixed controls evaluated

- 48 evaluation tasks x 4 seeds x 4 arms x 30 executor actions
- `deepseek/deepseek-v4.1-flash` via the locked OpenRouter DeepSeek-only route
- 1024 maximum completion tokens per model call
- Conservative OpenRouter endpoint price ceilings recorded for the DeepSeek
  route: USD 0.30 / million prompt tokens and USD 1.20 / million completion
  tokens.
- The existing protocol's conservative per-call prompt bound of 6,144 tokens
  is used below. It is more favorable than an unbounded conversation estimate.

## Evaluation alone

```
evaluation calls = 48 x 4 x 4 x 30 = 23,040
maximum completion tokens = 23,040 x 1,024 = 23,592,960
maximum prompt tokens = 23,040 x 6,144 = 141,557,760
completion cost = 23.592960M x USD 1.20/M = USD 28.311552
prompt cost     = 141.557760M x USD 0.30/M = USD 42.467328
evaluation-only bound                         = USD 70.778880
```

This excludes every acquisition call, ReMe/CoProMem lifecycle call, the two
OpenRouter canary records, and any retained reservation. It therefore exceeds
the USD 35 hard cap by USD 35.778880 before those required costs are included.

## Consequence

The requested workload cannot be registered honestly under USD 35. Reducing
the ceiling through expected early stopping would violate the stated controls;
neither task selection nor a paid call is authorized until the workload,
token/action cap, price ceiling, or hard cap is explicitly revised.
