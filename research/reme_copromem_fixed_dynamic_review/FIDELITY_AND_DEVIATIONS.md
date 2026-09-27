# Fidelity and deviations

ReMe preserves the pinned upstream AppWorld invocation boundary through its
service and executor wrappers. The locked transport, embedding boundary,
JSON-lines AppWorld process, and durable persistence are compatibility
infrastructure. This is therefore a faithful adaptation, not an exact paper
reproduction.

CoProMem uses its shared core directly. Prior integrations had an
offline/fallback-heavy construction path; this maintained source tree records
that limitation without importing prior state, cache entries, or results.
