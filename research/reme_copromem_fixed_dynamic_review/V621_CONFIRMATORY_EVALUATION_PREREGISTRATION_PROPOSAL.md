# Proposed v6.2.1 confirmatory evaluation

This is a proposal, not a frozen manifest or authorization to access tasks.

## Design

Use a new representative held-out allocation selected before payload access and without compatibility conditioning. Compare No Memory, CoProMem v6.2.1 Fixed, CoProMem v6.2.1 Dynamic, official upstream ReMe Fixed, official upstream ReMe Dynamic, and a preregistered shuffled or deliberately mismatched CoProMem-memory ablation. Allocate identical fresh tasks and three stochastic trials to every arm.

The minimum useful design is 30 tasks by three trials (540 trajectories across six arms). A 60–100 task design is preferred when budget permits because task-level paired bootstrap intervals then become more stable. Do not interpret any engineering diagnostic task as confirmatory evidence.

## Preregistered analysis

Freeze public-only task sampling, exposure exclusions, ordering, seeds, prompts, tools, routes, token/action limits, scoring, state transitions, and all bank identities before payload access. Report Avg@3 and Pass@3 with explicit denominators, paired task-level bootstrap confidence intervals, win/tie/loss, family-level summaries, actions, tokens, latency, cost, retrieval coverage, empty retrieval, prompt overhead, semantic relevance, Dynamic-prefix state identities, and all failures.

The shuffled/mismatched ablation must use a deterministic, task-independent assignment and preserve the same prompt budget and retrieval rendering. It tests whether a compatible memory association matters more than arbitrary memory text; it is not an invitation to tune or select memory after outcomes.

## Claims

Permitted claims require completed, reconciled evidence and uncertainty estimates: comparative performance under the frozen sampled distribution, retrieval coverage, and observed efficiency/cost differences. Prohibited claims include paper reproduction, universal superiority, causal mechanism beyond the registered ablation, and generalization outside the sampled benchmark families.

## Pre-dispatch gates

Before a paid confirmatory run: verify fresh-task custody; all bank/runtime identities; ledger and hard-cap bound; Fixed immutability; Dynamic checkpoint recovery; reproducible retrieval; empty-guidance prompt identity; mismatched-ablation assignment; evidence-journal binding; and final-report reconciliation. No manifest, payload access, or runner is created by this proposal.
