# Evaluation 005 interruption audit

`v6_1_exploratory_diagnostic_evaluation_005_clean_restart` is retained as an
infrastructure-interrupted audit run.  It must not be resumed: the runner was
interrupted after the first trial batch had begun, before its live summary met
the required per-trajectory refresh contract.

Two scored artifacts (No Memory and ReMe Fixed, task `57c3486_2`, trial 1)
are retained as audit evidence only.  They, all associated calls, and the
unfinished Dynamic trajectory are excluded from every future evaluation state
and comparative analysis.  The source repair in `37abd9de` refreshes the
summary immediately after each scored artifact; it does not alter any method
or scientific parameter.

Any future complete clean successor requires a separately versioned manifest
and an explicit carry-forward of this run's settled exposure and unresolved
reservation.  Nothing in this document imports or modifies the run directory.
