# Audit of the former 1,190,880-call upper bound

## What the number counted

The former number was an executor-only *worst-case iteration-call* count.  It
was not a count of independent tasks, trials, trajectories, or summarizer
calls.  One agent iteration was treated as one paid executor completion; each
trajectory/trial could consume up to 30 such completions.

| Benchmark / phase | Arms | Tasks | Samples or trials/task | Iterations/sample | Seeds | Executor calls |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BFCL acquisition | 5 memory arms | 50 | 8 trajectories | 30 | 3 | 180,000 |
| BFCL evaluation | 6 arms | 150 | 4 independent trials | 30 | 3 | 324,000 |
| AppWorld acquisition | 5 memory arms | 90 | 8 trajectories | 30 | 3 | 324,000 |
| AppWorld evaluation | 6 arms | 168 | 4 independent trials | 30 | 3 | 362,880 |
| **Former total** | | | | | | **1,190,880** |

The arithmetic itself was correct.  The design assumption was not: acquisition
was multiplied by five memory arms.  At acquisition all memory arms use the
same no-memory executor, task information, tools, seed, temperature, and
iteration ceiling.  Re-running it for A-Mem, LangMem, ReMe-fixed,
ReMe-dynamic, and CoProMem would give each method duplicated, differently
sampled experience rather than matched information.

## Corrected full-study executor bound

Generate raw acquisition trajectories once per benchmark/seed and fan them out
to method-specific distillers.  ReMe fixed and dynamic also begin with the same
frozen initial ReMe pool; only dynamic may change it during evaluation.

| Component | Calculation | Executor calls |
| --- | --- | ---: |
| BFCL acquisition | 50 x 8 x 30 x 3 | 36,000 |
| BFCL evaluation | 150 x 4 x 6 x 30 x 3 | 324,000 |
| AppWorld acquisition | 90 x 8 x 30 x 3 | 64,800 |
| AppWorld evaluation | 168 x 4 x 6 x 30 x 3 | 362,880 |
| **Corrected executor total** | | **787,680** |

This saves 403,200 executor calls.  It does **not** reduce the required four
independent evaluation trials: those are repeated measurements of each
held-out task and remain separate for every arm and seed.  It also does not
claim that individual agent iterations are independent observations.

## Model roles omitted from the former total

The former bound omitted paid calls for (a) ReMe success/failure/comparative
distillation, validation, and reflection, and (b) any optional CoProMem LLM
decomposition.  A final full-study estimate must add explicit caps for these
roles.  The development pilot below does so.  AppWorld's official scorer is
deterministic and adds no model judge call.

## Controls against repeated acquisition

* Store a raw trajectory manifest keyed by benchmark, development task ID,
  seed, sample index, executor request hash, and terminal score.
* Generate the shared acquisition pool before creating any arm-specific memory.
* Disallow memory writes during primary evaluation except ReMe-dynamic's
  preregistered utility/deletion metadata behavior.
* Assert identical raw-pool hash for ReMe-fixed, ReMe-dynamic, and CoProMem;
  A-Mem and LangMem consume the same pool but retain only the method-prescribed
  successful trajectories.
* Count malformed outputs and retries inside the 30-iteration ceiling; no
  hidden retry budget exists.
