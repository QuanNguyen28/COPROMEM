# AppWorld public-interface fidelity audit

Recorded 2026-09-16 during the frozen cycle-6 source collection. This is a
non-interventional code/document review. No cycle-6 prompt, sample, source runner,
runtime image or scoring rule was changed as a result of this inspection.

## Primary-source findings

The [official AppWorld walkthrough](https://github.com/StonyBrookNLP/appworld#-task-worlds)
permits supplying task instructions, supervisor profile, app descriptions and
public API documentation in an agent's initial context, or retrieving the same
information through public tools. Hidden task ground truth is separate and must
not be presented as agent context. Therefore, upfront public onboarding is a
legitimate shared-adapter choice, not privileged oracle information.

The [official minimal-agent notebook](https://github.com/StonyBrookNLP/appworld/blob/08132046efd85186e250e270d061a04d719605ee/notebooks/minimal_agent.ipynb)
uses a much richer onboarding prompt than cycle 6. It illustrates documentation
discovery and credential retrieval with dummy data, requests small raw Python
chunks, identifies how answer-seeking tasks are completed, and supplies the
supervisor's public identity. It also explains pagination, temporal boundaries,
and simulated file-system access. These are manually provided baseline
instructions, not automatically learned memory. The notebook's last file-change
revision was independently resolved through the official GitHub API to the commit
in this link (2025-04-21).

Only the notebook's generic prompt/class source was inspected; notebook execution
outputs and benchmark solution programs were not used. The example uses dummy
credentials, not a source/evaluation task solution. No reserved scenario was
opened by this audit. Native public supervisor documentation was also checked:
profile, account-password, active-task and completion APIs are available.

## Contrast with the implemented collection protocol

Cycle 6 provides short role prompts and tool-discovery signatures to the executor,
but no worked onboarding interaction. The planner is asked to plan using observed
documentation while initially seeing none. Supervisor identity is not included
upfront, though it remains retrievable through the public profile API. The
executor must serialize its Python program inside a JSON string, creating an
additional escaping requirement that the official raw-code example does not
have. It can still submit raw code through an explicitly recorded fallback.

The instruction that the task is solved through app state changes is incomplete
for answer-seeking tasks: those legitimately finish by supplying the requested
answer, without an unrelated app mutation. The prompt does mention a documented
completion API, but does not give the answer-bearing signature. This is a common
adapter weakness, not a CoProCon defect or a learned-contract opportunity by
itself.

These omissions do not make public information inaccessible in principle.
However, discoverability, representation and extra reasoning burden can materially
affect a small model. A weak no-memory agent is not a sufficiently strong baseline
merely because its tools are technically available. The official notebook is a
useful reference, not an exact reproduction of the fixed two-role team here.

## Consequences for the next protocol

1. Finish and report the current registered sample without altering it mid-run.
2. Audit malformed output, truncation, caught errors and code that produces no
   calls separately from native task success. These are descriptive diagnostics,
   not new primary outcomes.
3. Before testing memory, give every arm a common, explicit public onboarding
   contract: small executable chunks, discovery instructions for both roles,
   correct completion semantics, and the same allowed public profile/docs.
4. Consider raw Python executor output to remove an unnecessary JSON-string
   serialization obstacle. Register it as an adapter change, never as learned
   procedural memory or an efficacy gain.
5. Test the revised no-memory workflow on build data first. Keep the original
   failed protocol and costs in the record. A stronger backend sensitivity test
   may follow if the same basic failures remain; do not silently switch models.

No API-schema rule, pagination instruction or correct completion signature taken
from public documentation may be relabelled as automatically learned decisive
logic. Strong static controls must have access to this same baseline knowledge.
The eventual scientific question remains downstream value of a learned scoped
intervention beyond a competent common workflow and its static controls.
