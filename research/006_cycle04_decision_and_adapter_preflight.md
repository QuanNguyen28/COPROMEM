# Cycle 4 decision and stateful-adapter preflight

Date: 16 September 2026. Branch `codex/copromem-research-loop`.

## Cycle 4: REVISE

The offline audit used all eight saved cycle-1 development checkpoints. Static and
sham each activated on four. All four had successful no-memory outcomes; therefore
schema-violation precision for baseline failure was zero, and the schema false
positive rate among baseline successes was 4/8. Both policies produced zero
beneficial and one harmful flip: one harmful outcome out of four activations.

Static spent four extra logical calls and USD 0.00017380; sham spent four extra
logical calls and USD 0.00016118. These are counterfactual arm-level cost differences,
not new bills. The audit used no additional API calls or cost. It reinforces the
separation of schema validity from repair value; it does not train an uplift model
or validate a new agent. Both minimal descriptive benefit gates reject promotion.

Artifact: `artifacts/research/cycle04_offline/intervention_audit/ff8a315766db9764810f1fb30dd024a60d156c961f9e4b4f775e34311d46c820.json`.

## Next bounded step: AppWorld setup and adapter feasibility only

No full benchmark experiment or new paid request is authorized by this preflight
configuration. Install the public released package `appworld==0.1.3.post1` into a
new repository-local Python 3.12 virtual environment, not the user's global Python.
The verified PyPI wheel SHA-256 is
`db77f8003982502383a50fa2974983894bd1c54f64e2fd3f7e1540d5edd037eb`.
Record the actual resolved dependencies; current upstream main is a different
development version and must not be confused with this release.

Check imports/CLI first. Any subsequent data probe must use train IDs only and
authored, reviewed actions—not arbitrary LLM-generated Python on the host.
Keep safety guards enabled. Real model-generated execution requires a container
or equivalent isolated environment with no API key or user workspace mount.
The Docker Linux daemon is currently stopped. Do not silently disable isolation.

Fairness constraints from the [official AppWorld guide](https://github.com/StonyBrookNLP/appworld):
test sets are aggregate-evaluation only; task-specific test inspection/tuning is
excluded. Native state restore may be used by the **evaluation harness** to fork
identical experimental states, not exposed as an extra capability to one agent.
Use unique output directories because world initialization can clear a prior run.
Do not hardcode benchmark-specific API calls into a compared agent's policy.

Setup success establishes only adapter feasibility. It cannot override the
mechanism/novelty gates or justify scaling experiments.
