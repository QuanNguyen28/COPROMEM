# fixed_dynamic_v4: sanitized review package

## Research question

The experiment compares no memory, official-upstream ReMe Fixed, official-upstream ReMe Dynamic, CoProMem Fixed, and CoProMem Dynamic under a common AppWorld executor and official scorer.

**Acquisition** is the shared collection of 32 trajectories used to construct memory. **Evaluation** is the held-out execution phase. The completed run evaluated 16 tasks, four seeds/trials per task, five arms, and therefore 320 trajectories (64 per arm).

The executor route was OpenRouter `deepseek/deepseek-v4.1-flash`, pinned to the DeepSeek provider with fallback and reasoning disabled. ReMe embeddings used OpenRouter Azure `openai/text-embedding-3-small` at 1024 dimensions.

`AvgScore` is the mean official AppWorld score, including fractional scores. `SuccessRate` is the proportion with full official score 1.0. `Successes` is the corresponding full-score count. `AvgActions` is the mean executor action count. All 320/320 registered trajectories completed.

Read [FINAL_REPORT.md](FINAL_REPORT.md) with [statistical-analysis.json](statistical-analysis.json). The inference is exploratory: it cannot support a superiority, task-family-generalization, or exact-paper-reproduction claim without supporting paired corrected evidence.
