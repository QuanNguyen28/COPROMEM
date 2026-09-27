# Known issues

- v4 instantiated CoProMem adapters with `api_key=""`; native LLM
  decomposition was therefore disabled.
- 48/52 observed retrievals per arm used generic fallback; only four
  retrievals from one task used learned/structural guidance.
- Fixed and Dynamic produced identical guidance hashes across all 52 completed
  paired retrievals.
- v4 must be labeled an **offline/fallback-heavy diagnostic ablation**, not a
  method-superiority result.
- Selected-memory IDs and candidate scores are not fully persisted.
- ReMe internal retrieval provenance is not durably captured per trajectory.
- The current ReMe setup is a DeepSeek/embedding adaptation, not an exact
  paper reproduction.
