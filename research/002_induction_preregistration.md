# Cycle 2 preregistration: bounded trace induction

Date: 2026-09-16, before inspecting cycle 2 outcomes.

## Hypothesis

Generic structural predicates mined from same-task, same-public-context success/failure
handoffs can recover useful artifact constraints without encoding decisive field names
in the induction algorithm. The strongest alternative is that the learner merely
rediscovers the schema already stated in the planner prompt, with no learning advantage.

Candidate proposal must use **build** traces only. Match exact task/context, not pooled
outcome counts. Restrict the initial language to presence, nonempty values, JSON types,
and homogeneous list element types. Field paths come from observed artifacts. This is
structural invariant mining, not unrestricted semantic verifier synthesis.

Scope initially uses the observed interface and optional public categorical context.
GSM8K provides no independently validated procedural-family labels; do not claim
semantic scope learning from its benchmark name.

## Predeclared gates

- At least two distinct source tasks with matched positive/negative handoffs.
- A candidate must accept its matched successful artifacts and reject failed artifacts.
- No final or audit traces may enter proposal or clause selection.
- Select/minimize on development replay; freeze before independent boundary audit.
- Admission requires at least four unique development tasks, one beneficial flip,
  positive net development effect, zero development harmful flips, and at least two
  independent boundary tasks with zero harmful flips.
- Save rejected candidates, source checkpoint IDs, scope, every replay and its cost.
- Do not silently relax gates if an empty bank results.

These are **pilot engineering gates**, not statistically powered proof of safety or
superiority. A later confirmatory study requires prospective sample-size planning and
uncertainty bounds.

## Controlled comparison

Use the identical planner checkpoint, provider route, recovery prompt constructor,
decoder caps, solver, and evaluator for induced versus static contracts. A static
schema and an induced copy of that same schema must receive identical outcomes when
their effective requests match. An advantage over no memory alone does not pass.

## Falsification and decision

- No matched pairs or no discriminative predicates: reject induction for that corpus.
- Dev or boundary harm: reject candidate.
- Static ties induced under identical predicates: retain runtime, reject accuracy-win claim.
- Source-field names manually embedded in learner: invalidate the learning claim.
- Positive mocked outcomes prove only implementation behavior.

Start with local fixtures spanning different field names and harmless missing-field
boundary cases. Real source collection uses disjoint GSM8K training partitions;
no current final test set is opened.
