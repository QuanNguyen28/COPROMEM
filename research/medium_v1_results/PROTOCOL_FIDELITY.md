# medium_v1 protocol and fidelity note

This is a completed 40-task × 4-trial × 4-arm diagnostic experiment (640
evaluation trajectories), using the frozen `medium_v1` manifest. It reused
five immutable acquisition artifacts from six registered acquisition slots;
it did not replay acquisition.

Executor route: OpenRouter `deepseek/deepseek-v4.1-flash`, DeepSeek-only,
fallback disabled, non-streaming, reasoning disabled, 1,024 completion-token
ceiling and 30 actions. ReMe embeddings used OpenRouter Azure
`openai/text-embedding-3-small` at 1,024 dimensions. The native AppWorld
worker and official scorer ran in the separate pinned AppWorld environment.

ReMe source is pinned to `agentscope-ai/ReMe` commit
`2f37a159b72a04ac1885a7db7f1a663a833e7791`, source digest
`5d2706b7b0e304475c71778b9336a733874e2492f4fdb5d311a2914751fe47fa`.
The split-process transport and runner adaptation mean the ReMe arms are
faithful adaptations, not exact paper reproductions.

Critical limitation: ReMe retrieval was empty and CoProMem evaluation was
called with empty intent, so its injected guidance was generic or empty. This
is therefore a diagnostic execution result and cannot support a
method-superiority, transfer, or generalization claim.
