# Cycle 4: offline repair-effect diagnostic

Date: 16 September 2026, before running the new diagnostic.
Branch and base commit are unchanged from cycles 1–3.

This cycle uses **all eight paired development checkpoints** from cycle 1, not a
subset chosen by correctness. No new external requests, final data or benchmark
installation is involved. Budget: USD 0. No parameters or candidate rules will
be fitted; prior cycle-1 outcomes are already known, so this is an explicit
retrospective formulation audit, not prospective confirmation.

Hypothesis: schema violations and observed repair benefit are distinct targets;
a rule predicting the former need not improve the latter. Compare the saved static
and sham controls to their exact saved no-memory continuations. Preserve paired
task-level bootstrap intervals and all beneficial/harmful/no-change outcomes.

Report violation counts, baseline failure among violations, harmful/beneficial
repair rates, extra logical calls and USD, and checkpoint/request identity.
The minimal descriptive benefit gate is at least four unique tasks, at least one
beneficial flip and zero harmful flips. It is **not** a calibrated admission rule
or a submission-level significance test. Reject final/audit data and mismatched
checkpoints. Identical cached solver requests cannot legitimately differ in score.

Expected falsifier: no beneficial repair, or any harmful flip, rejects promotion of
these repair policies. Either outcome cannot establish how a learned stateful
contract performs; the next question remains a new-domain mechanism test, not a
claim that this audit itself improves the agent.
