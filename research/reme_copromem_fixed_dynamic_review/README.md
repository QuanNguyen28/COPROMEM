# CoProMem / ReMe Fixed-Dynamic review package

This branch is a clean review package assembled from `origin/main`, with a
minimal dependency-complete import of the fixed/dynamic integration code. It
contains no pilot artifacts, task payloads, provider responses, ledgers,
credentials, environments, or caches.

The code is organized as an installable `copromem` package. Only two
test-reachable AppWorld compatibility re-exports remain; all maintained code
uses canonical package paths.

See [MINIMAL_SOURCE_MANIFEST.md](MINIMAL_SOURCE_MANIFEST.md),
[ARCHITECTURE.md](ARCHITECTURE.md), [FIDELITY_AND_DEVIATIONS.md](FIDELITY_AND_DEVIATIONS.md),
and [KNOWN_ISSUES.md](KNOWN_ISSUES.md).
