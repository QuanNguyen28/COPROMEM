# Proposed v5.1 observable-supported-subgraph rule

This is a proposal only. It is not applied to v5 runs, including 005 and 006.

## Motivation

V5 requires every normalized operation to be observed. In real AppWorld
traces, public helper/auth/read actions can include a branch, loop, or nested
expression even when the descriptor-required procedure is directly observed.
The result is a conservative but frequently non-learning bank.

## Separate v5.1 amendment

Before any new run, freeze a public descriptor and an exclusion registry. A
v5.1 promotion would require:

1. Every descriptor-required operation/slot edge is directly observed in the
   public history.
2. Each promoted procedure has its own public response evidence and remains
   content-addressed to that evidence.
3. A helper can be excluded only if it matches a frozen public category (for
   example, an API-documentation lookup with no dataflow into a promoted
   procedure). Exclusion is recorded in the plan.
4. Unobserved descriptor steps, unknown helpers, and nonmatching operations
   remain candidate/quarantined. They never enter injected guidance.
5. No private scorer state, reference answer, concrete acquisition value, or
   post-execution hidden evidence may influence the subgraph.

The v5.1 selector must be versioned, deterministic, and tested against
counterexamples for nested/loop code. It is a method amendment, not a repair
to the transaction bug, and requires its own fresh-task protocol and explicit
authorization.
