# v6 shared acquisition 001

This protocol creates a common, no-memory AppWorld **train** acquisition pool only. It excludes `test_normal` and contains no evaluation or method-comparison claim.

Before payload access, the standalone runner computes a custody audit, excludes only task IDs with execution or scoring evidence, selects six public families with two canonical siblings each, and freezes 12 IDs with seeds 10101 and 10102. The resulting 24 trajectories use the locked DeepSeek-only OpenRouter route, public-execution-evidence v1, the native worker, official scorer, a 30-action limit, and a USD 100 fail-closed ledger.

After every trajectory is terminal and scored, the same frozen pool is supplied independently to the pinned upstream ReMe construction service and to CoProMem v6 response-attested contrastive graph construction. ReMe and CoProMem content is never mixed. Evaluation is prohibited unless all pool and bank gates pass.
