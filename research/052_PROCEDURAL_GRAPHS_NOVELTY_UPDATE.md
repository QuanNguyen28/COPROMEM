# Focused novelty correction after cycle 22

Recorded 2026-09-16. This adds a previously omitted close paper; it does not
rewrite the earlier audit or claim an exhaustive search.

## Verified primary-source findings

[Procedural Graphs: Self-Evolving Execution Structures for LLM Agents,
arXiv 2609.09153v1](https://arxiv.org/abs/2609.09153) was submitted on 8 September
2026. The inspected [method, sections 3.1--3.3 and appendix C](https://arxiv.org/html/2609.09153)
stores attributed procedure transitions. A guidance model reads a localized
neighborhood and recent trajectory; its output conditions the solver prompt.
This is soft guidance, not deterministic enforcement of artifact predicates.

Offline refinement compares high- and low-scoring training trajectories and
proposes graph edits. Structurally valid candidates receive fresh validation
rollouts; their measured scores are compared with the retained graph's cached
score. Rejected edits are recorded. Thus this gate is not merely a surrogate
score on historical actions. The inspected procedure does not establish matched,
immutable upstream checkpoints for the candidate/reference comparison.

The inspected primary pages and targeted repository search did not verify an
official implementation URL. Code availability remains unverified, not absent;
no implementation or numerical result was reproduced.

## Consequence for our own claim

The combination of contrastive procedural edits and downstream validation cannot
serve as our novelty nucleus. This corrects any reading of earlier local notes
that would generalize the Skill-Pro implementation distinction to all prior art.
Skill-Pro's inspected historical surrogate remains that implementation's finding;
it does not establish that fresh rollout validation is unoccupied research space.

Our remaining hypothesis is narrower and still unproven: an automatically
derived executable boundary check, whose applicability and specific recovery
benefit survive matched intervention and benign-boundary tests, may improve a
fixed workflow beyond the same runtime with strong human-authored checks. That
requires actual learned logic, attributable effect and disjoint-task transfer.
It cannot be inferred from a renamed memory object or from a passing audit.

The current repository has two automatically constructed local repairs, no
admitted stateful contract bank, a failed AST-count predicate screen and a
working standard missing-name control. It has not demonstrated the proposed
distinction or a quality/efficiency advantage. These are repository observations,
not claims about another paper's performance.

## Decision and next experiment boundary

**REVISE the novelty claim; retain the tested infrastructure.** Do not replace
the baseline with a weaker home-written checker or add graph structure simply
to change terminology. The next implementation should test evidence-derived
procedural discrimination on failures left by the standard checker, with a
competent manual semantic comparator and success-only ablation. If it only
matches a hand-specified rule, report that result; do not claim reduced authoring
effort without measuring it. Candidate construction and build consistency must
remain separate from recovery/admission and untouched-group evaluation.

This focused update makes no new API calls and changes no native policy,
evaluator, split, original research document or frozen experiment source.
