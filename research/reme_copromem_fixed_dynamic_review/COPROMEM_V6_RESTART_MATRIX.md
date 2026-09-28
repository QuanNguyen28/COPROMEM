# v6 restart matrix

| Last durable transition | Resume behavior |
| --- | --- |
| none / initialized | freeze the registered task pre-state |
| pre-state frozen | materialize only missing retrieval records |
| retrievals materialized | execute only missing trajectory artifacts |
| trajectories complete | persist only missing batch, plan, and validation records |
| validation persisted | commit the persisted plan once |
| commit persisted | load post-state; do not repeat lifecycle work |
| rejected finalized | leave state byte-identical and permanently block B |

Each path reconciles the append-only ledger first. An unsettled reservation,
missing scorer evidence, telemetry mismatch, or state/hash mismatch stops before
any dispatch.
