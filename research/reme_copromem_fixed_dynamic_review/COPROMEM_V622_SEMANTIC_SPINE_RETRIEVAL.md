# CoProMem v6.2.2 semantic-spine retrieval

This is a versioned repair for three executor-facing v6.2.1 retrieval defects. The v6.2.1 implementation and its prior engineering evidence remain unchanged. The v6.2 common-core learning and winner policy are also unchanged.

1. A schema is projected backward from its terminal effect. A preceding operation is retained only through same-app public dataflow or a declared registry dependency. A declared cross-app prerequisite also requires the app to be publicly relevant to the task. External input slots need a supported task-query operation and matching non-generic slot concepts, or a prior response-attested output. Otherwise retrieval abstains. Matching slot names across applications never establish dataflow. Guidance marks any external task value as requiring verification before use; semantic compatibility alone does not prove that a concrete value is available.
2. Schema IDs and historical success counts cannot decide which of two compatible procedures fits the current task. Distinct nonterminal operations explicitly supported by the public task query are the only tie evidence. A remaining tie returns empty guidance with `semantic_tie_abstention` provenance.
3. Each retained occurrence has a position and occurrence ID. The projection follows public dependencies both backward into the terminal effect and forward into response-attested verification steps after it. The guidance renderer emits every retained occurrence in order, including read → write → read when the write is the terminal effect. Positional typed constraints must cover the entire required sequence. Retrieval provenance records the exact projection and is reproduced offline before the versioned runner returns guidance.

The separate `run_v622_semantic_spine_engineering.py` entrypoint requires a v6.2.2 allocation audit bound to this policy. No v6.2.1 runner or immutable engineering run is migrated automatically. These tests and this method repair do not establish efficacy or authorize a paid run.

## Windows fixture note

`python -m pytest tests/reme_copromem/test_task_boundary_v6.py -ra` prints `4 passed` but exits with code 1 on this Windows host and emits no traceback. The cause is independent of pytest and v6.2.2: `python -c "import os; print(os.kill(os.getpid(), 0))"` prints `None` and exits with code 1. The old fixture's duplicate-lock case calls exactly that Windows-incompatible PID probe. This is a pre-existing platform fixture issue, not a v6.2.2 regression. The fixture was not changed or suppressed here.
