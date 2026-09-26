# Official upstream ReMe scaled-fidelity pilot — pre-dispatch blocker

Status: **stopped before manifest task selection, payload access, model/API
calls, acquisition, or evaluation.** The local ReMe-adaptation exploratory
process was stopped and its existing journals were preserved when this request
superseded it.

## Verified upstream provenance

- Remote: `https://github.com/agentscope-ai/ReMe.git`
- Commit: `2f37a159b72a04ac1885a7db7f1a663a833e7791`
- Checkout: clean.
- Supplied tracked-content SHA-256 verified:
  `5d2706b7b0e304475c71778b9336a733874e2492f4fdb5d311a2914751fe47fa`.
- Official AppWorld sources were imported from
  `/home/xiqhq/copromem-reme/benchmark/appworld/appworld_react_agent.py` and
  `run_appworld.py`, not the local adaptation.

## Concrete compatibility work completed

1. Reconciled MCP to `1.30.0`: this satisfies the pinned ReMe package's
   `mcp>=1.25.0` and retains AgentScope 1.0.20's required
   `streamablehttp_client` API. Installed `greenlet==3.5.6` for AgentScope's
   SQLAlchemy async path.
2. Installed the pinned `ray==2.58.0` in the verified AppWorld runner
   environment, allowing the upstream `@ray.remote` AppWorld agent import.
3. Installed the remaining explicit upstream AppWorld runner dependencies
   (`openai==3.19.2`, `jinja2==3.1.6`, `loguru==0.7.3`) in that runner
   environment. The upstream agent and runner then imported directly from the
   pinned checkout.

The source's AppWorld and ReMe/AgentScope dependencies are mutually
incompatible in one environment (AppWorld requires Pydantic 1; ReMe/AgentScope
requires Pydantic 2), so the authorized minimal boundary is required: upstream
AppWorld runner in the native AppWorld environment and upstream ReMe service in
the E-backed ReMe environment.

## Exact blocker

Importing the pinned upstream ReMe service reaches
`reme_ai/agent/react/agentic_retrieve_op.py`, which imports `flowllm`. The
source declares it at `pyproject.toml:105` as `flowllm[reme]>=0.2.0.10`, but it
is absent from the prepared environment. This is the next, fourth undeclared
compatibility installation after the three permitted concrete repairs.

The attempted merged AppWorld install also left the E-backed ReMe environment
with Pydantic-1-era packages; its `pip check` reports incompatibilities with
the ReMe/AgentScope/MCP stack. It must be rebuilt or restored from its pinned
manifest before further upstream service work. No cleanup was performed so the
state remains auditable.

## Decision

**BLOCKED / no paid pilot dispatched.** Per the registered three-fix limit,
no `flowllm` installation, model canary, task manifest, AppWorld payload
access, or paid call was attempted. A future authorization would need to allow
a clean ReMe-service environment restoration plus the source-declared
`flowllm[reme]` dependency, followed by a fresh provenance and `pip check`
audit.
