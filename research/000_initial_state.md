# Research loop: initial state and cycle 1 preregistration

Recorded 2026-09-15 22:59 UTC (2026-09-16 Asia/Ho_Chi_Minh).

## Provenance and preservation

- Original branch: `codex/empty`.
- Original HEAD: `18025102c010e85f26b0b3fb1144a1cb684b587e` (latest commit: `doc`).
- Research branch: `codex/copromem-research-loop`, created from that HEAD.
- Initial tracked/untracked status: clean. Ignored caches remain in place.
- No commits, pushes, merges, PRs, or history changes authorized.
- Preserve existing reports as historical evidence; new reports go under `artifacts/research/`.
- Protected document SHA-256:
  - `docs/CoProCon_research_doc.md`: `1C8D63B16079F9CA96EC2E690CDABA31118DF6751A178BC9CDB394F1FD3BA73A`.
  - `docs/CoProCon_research_doc.docx`: `AF2ACF33C597E014482889CF731B75D293ED9B3FB0C0FCFF5A7FDFBC5F3CB5C3`.
- Python 3.13.5; `PYTHONPATH=src python -m pytest -q`: 12 passed.
- Ruff: 36 pre-existing, auto-fixable findings; no functional interpretation.
- No API key found in the process environment or project/parent `.env`; no paid requests issued.

## Observation

The original real runner independently generates each arm's planner output. Aggregate
success/failure counts admit a predefined three-field schema. Neither fact establishes
learning value. Literature runners also remain adaptations and cannot be described as
exact reproductions. Vendor gitlinks have pinned commits but no `.gitmodules`.

## Cycle 1 hypothesis (predeclared)

**Claim:** immutable upstream snapshots and content-addressed matched downstream requests
can remove implementation-induced differences between scientifically identical arms.
This is an engineering/identifiability claim, not a task-quality claim.

**Mechanism:** generate planner once per task/rollout; freeze the complete public artifact;
resume all arms from its digest; use identical solver requests when their effective
artifact/context is identical. Cache reuse is reported separately from counterfactual
per-arm logical cost. Seeds are matched by stage and repetition, never by arm name.

**Strongest competing explanation:** provider sampling and shared mutable state can
create apparent treatment gains even without an intervention. Matching upstream alone
does not eliminate downstream provider nondeterminism.

**Support:** all checkpoint hashes match; malicious mutation cannot affect another arm;
identical effective requests share the same saved response; reordered arms give identical
results; failures are logged and do not corrupt other arms; physical/logical costs reconcile.

**Falsification:** any mismatch, cross-arm contamination, outcome dependence on arm order,
unlogged retry, silent dropped task, or different evaluator invalidates the pilot.

**Smallest experiment:** scripted provider with malformed and complete planner outputs,
stateful/nondeterministic solver, one injected provider failure, all six control arms.
No external API budget is needed for this cycle. Mock accuracy is never empirical evidence
of method quality.

**Arms:** no intervention; success-only memory at the shared handoff; textual corrective
memory at the shared handoff; schema-triggered sham retry; static schema verification and
targeted recovery; historical observational schema contract (explicitly not learned).
Genuine induced contracts replace the last arm only after cycle 2 validation.

**Primary metric:** violated causal invariants (required value 0). Secondary: persisted
request/checkpoint completeness, paired flips, physical calls versus logical calls.

**Split policy:** use local fixtures first; future real development uses a predeclared
partition of GSM8K training data. Existing published test slices are already inspected
and are not a fresh confirmatory final set. No final-test tuning.

## Next cycle

Induce restricted predicates from same-context success/failure pairs, validate on disjoint
development and boundary checkpoints, and compare to static checks using the same runtime.
Run primary-literature audit before adopting a paper novelty claim.
