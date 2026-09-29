# v6.2 medium held-out exploratory protocol

`v6_2_task_conditioned_evaluation_001` is a separately frozen, 30-task
`test_normal` exploratory evaluation.  It uses five arms, two ordered
stochastic trials per task, and a task-major dispatch order: both No Memory
trials, both ReMe Fixed trials, both sequential ReMe Dynamic trials, both
CoProMem Fixed trials, and both task-batch CoProMem Dynamic trials.

Before task payload access, selection uses only the public ID inventory and a
behavioral custody classifier.  The public-family round-robin rule selects 30
previously unopened IDs.  Once frozen, all selected IDs are permanently
exploratory-exposed.  This is compatibility-conditioned exploratory sampling,
not an unbiased benchmark sample.

The USD 300 cap includes historical exposure, registered executor, ReMe
lifecycle, and Azure embedding ceilings plus a non-dispatchable 15% margin.
No CoProMem decomposition call is registered because the v6.1 semantic bank is
loaded unchanged.  The report uses task-level deterministic bootstrap intervals
and treats CoProMem Dynamic vs official ReMe Dynamic as the designated primary
comparison.  It makes no confirmatory, superiority, or generalization claim.
