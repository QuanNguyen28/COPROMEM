# medium_v1 40-task budget gate

No `medium_v1` directory or partial 30-task manifest existed at audit time.
No task payload was opened and no paid request was dispatched.

The locked OpenRouter route charges the conservative ceiling used by the
existing runner: 16,384 input tokens at USD 0.30/M plus 1,024 completion
tokens at USD 1.20/M, or **USD 0.006144 per generative request**.

| Registered component | Worst-case calls | Ceiling (USD) |
|---|---:|---:|
| Evaluation executor: 40 x 4 x 4 x 30 | 19,200 | 117.964800 |
| CoProMem decomposition cap | 320 | 1.966080 |
| ReMe construction (5 x fixed + 5 x dynamic) and dynamic post-trial summaries (160) | 170 | 1.044480 |
| Azure OpenRouter embeddings (490 x 16,384 tokens at USD 0.02/M) | 490 | 0.160563 |
| New-run dispatchable ceiling | — | **121.135923** |
| Existing immutable pilot exposure carried conservatively | — | 0.189716 |
| All dispatchable exposure | — | **121.325640** |
| 15% non-dispatchable contingency | — | 18.198846 |
| All-inclusive conservative ceiling | — | **139.524485** |

The executor component alone exceeds the USD 35 cap.  This protocol cannot
be frozen, task-selected, or launched without explicit authorization of at
least USD 121.325640 in dispatchable cap; USD 139.524485 is required if the
established 15% all-inclusive contingency is retained.
