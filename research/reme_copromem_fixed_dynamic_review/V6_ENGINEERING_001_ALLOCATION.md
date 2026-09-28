# v6 engineering 001 allocation protocol

This is an engineering-only, exposed train-split A→B validation, not an
efficacy or generalization study. Selection uses the prior public-only train
inventory and the frozen callable registry; it does not read execution results
or `test_normal`.

The allocator excludes only task IDs with durable execution artifacts, then
groups train siblings by a value-redacted public instruction template. It sorts
eligible pairs by `(descriptor_sha256, a_task_id, b_task_id)` and selects the
first pair exactly once. The resulting allocation audit, manifest, raw public
inventory references, and all runtime evidence remain local under `artifacts/`.

The registered design is two arms (`no_memory`, `copromem_v6_dynamic`), two
seeds, two train tasks, and at most eight trajectories. It starts with the
content-addressed empty v6 semantic state. No ReMe service or embedding route
is registered. The USD 100 fail-closed cap registers 240 executor calls (the
structural maximum) and zero calls for all other provider roles.
