# AppWorld development-only pilot: preregistered protocol

## Scope and isolation

This is a plumbing and headroom check, not an efficacy test and not a final
benchmark result.  It uses an AppWorld development subset drawn only from the
training pool.  It must never use `test_normal`, the final 90-task acquisition
set, or any final held-out manifest.  A deterministic manifest selects six
development-acquisition tasks and eight disjoint development-evaluation tasks
from a separately declared AppWorld training/development source.  Its source
revision, IDs, order, seed, and SHA-256 are written before execution.

One frozen run seed is used.  Primary arms are No Memory, ReMe fixed, ReMe
dynamic, and current `copromem_v2` CoProMem at
`6eca54ca14a7935fcdcdc1a9a77319ed113a0679`.  Every arm uses the same direct
DeepSeek non-thinking endpoint, tool schema/access, task text, 30-iteration
limit, sampling settings, transcript/input cap, and unchanged official
AppWorld scorer.

## Shared acquisition

For each of six acquisition tasks, generate exactly eight no-memory raw
trajectories at temperature 0.9 and no more than 30 executor iterations each.
The resulting 48 trajectories are frozen and shared across memory arms.
ReMe fixed and dynamic receive the same initial distilled pool. CoProMem
receives the same trajectory records using its current acquisition logic: it
starts with an empty acquired-memory bank, records every success and failure
episode, induces successful procedures as pending memories, and consolidates
schemas. Recursive decomposition, procedural-memory retrieval, pattern
separation, subtask-level binding, episode recording, and consolidation remain
enabled. It uses `include_contract_guidance=False`; generic default procedural
memories are disabled only in the comparison adapter as a fair-comparison
adaptation. No Memory receives no acquired memory or memory text.

At most three failure-reflection operations per acquisition task are allowed.
All unsuccessful, malformed, tool-error, and timed-out trajectories are
preserved.  The pilot does not support a general success/failure pairing claim:
it only verifies that each arm's documented path can consume the common pool.

## Evaluation

Evaluate eight development scenarios, distinct from acquisition, with four
independent trials per arm.  Retrieve once before each trial; no within-task
retrieval is allowed. Each trial has at most 30 executor iterations. With an
API key, native CoProMem decomposition remains active and has a registered
global 320-call ceiling. AppWorld
official scoring is the sole success definition.  Do not use an LLM judge.

The independent descriptive unit is the eight development scenarios.  Report
per-task trial outcomes, Avg@4, Pass@4, arm-specific failure categories,
trajectory/memory hashes, and separate acquisition/evaluation ledgers.  No
confidence interval, significance test, or superiority statement is licensed
by eight development scenarios.

## GO / KILL criteria

**GO to frozen full-study preflight only if all apply:** manifests are disjoint;
all four arms reach the official scorer; no arm receives unequal tools/task
information or an unlogged extra model call; raw-pool hashes agree; token/call
caps are respected; and no fatal parser, retrieval, memory-persistence, or
scorer defect appears in more than 1 of 8 scenarios for an arm.

**KILL / REVISE** if a scorer cannot be reproduced, a task leaks across
partitions, any arm cannot execute under the common harness, CoProMem receives
additional task-specific information/compute, the provider route differs
between arms, or the $20 hard ceiling would be exceeded.  A lower score alone
is not a kill criterion; it is diagnostic evidence only.

No paid execution is authorized by this file.  It requires the explicit
approval requested at its end.

## Exact arm lifecycle diagrams

```text
No Memory: task -> common executor prompt/tools -> official AppWorld scorer
ReMe fixed: shared raw acquisition -> distill/validate -> frozen pool ->
             retrieve once -> common executor prompt/tools -> scorer
ReMe dynamic: shared raw acquisition -> same initial pool -> retrieve once ->
               common executor prompt/tools -> scorer -> validated addition +
               retrieved-memory frequency/utility update -> alpha=5,beta=.5 prune
               (four independent dynamic state streams; no cross-trial leakage)
CoProMem v2: shared raw acquisition -> retrieve/decompose schema -> record every
              episode -> successful procedure pending -> consolidate/admit ->
              retrieve once + pattern separation + recursive/subtask guidance ->
              common executor prompt/tools -> official scorer
```

The CoProMem prompt is `common_prompt + registered_guidance` and differs from
No Memory only by registered decomposition/memory guidance. Contract guidance
is excluded and can only be a separately budgeted ablation.
