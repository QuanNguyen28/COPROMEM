# Engineering 009 exposed guidance replay amendment

`reasoningbank_appworld_engineering_009_exposed_guidance_replay` is an exposed
engineering replay.  The A/B/N triple is explicitly authorized for integration
validation of the C9 sealed-guidance repair and C10 native-path portability
repair.  It is not evidence of efficacy, superiority, transfer, generalization,
or held-out performance.

The executable source is C10 (`de9a173194d3e9be9be6955e2b47c178eba6cd68`).
This publication records allocation and custody only.  The external frozen
manifest binds C10 and this publication commit separately; it includes no
credential, payload, journal, completion, score, or generated trajectory.

Each of A `d4e9306_2`, B `d4e9306_3`, and N `df61dc5_3` receives two trials
under No Memory and official ReasoningBank Dynamic, for twelve new trajectories
from an empty initial bank.  No artifact, score, memory, retrieval, checkpoint,
or state is imported from Engineering 001--008.

The replay uses DeepSeek V4.1 Flash for executor, judge, and extractor; Azure
`openai/text-embedding-3-small` at 1024 dimensions with no fallback; official
top-1/no-abstention retrieval; the frozen temperatures and execution limits;
the official scorer; Dynamic checkpoint/restart policy; the USD 50 cap; and
the established storage policy.  Historical infrastructure exposure remains a
separate ledger category and is never assigned to an Engineering 009 arm.

Before each Dynamic executor dispatch, the runtime persists and verifies
content-addressed float32 query/candidate vectors, candidate ordering and
cosine scores, deterministic selection, canonical lifecycle-rendered guidance,
and an exact model-visible prompt binding.  Empty guidance is required to be
byte-identical to the No Memory prompt.  A detached runner may start only after
offline retrieval reproduction and source/runtime/manifest identity checks pass.
