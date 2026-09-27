# Fidelity and deviations

ReMe code preserves the pinned upstream AppWorld invocation boundary through
its service and executor wrappers. The surrounding transport, embedding route,
JSON-lines AppWorld boundary, and persistence are compatibility infrastructure.
Accordingly, this work is a faithful adaptation, not an exact paper
reproduction.

CoProMem’s shared core is used directly. The reviewed v4 integration used an
offline/fallback-heavy construction path; this reorganization preserves that
behavior rather than changing conclusions or experiment state.
