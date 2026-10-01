# Engineering 008 pre-dispatch NO-GO

Engineering 008's exposed-replay manifest was frozen before payload access, but
the required production-path provenance gate failed locally.  No ledger,
artifact, retrieval record, provider request, AppWorld task, scorer call, or
Dynamic checkpoint was created in the run.

The C8 fixture compared the pinned lifecycle's callback bytes with the bytes
returned by the C7 provenance callback for the same empty-state-preserving
top-1 retrieval.  They differed:

| Value | SHA-256 | Length |
| --- | --- | ---: |
| Pinned lifecycle callback | `229d9ab324f3e1a33c01365ff3faf2dda5c369f45fee23d5c30820330fac18ee` | 342 |
| C7 provenance callback | `4b548a43c5eb21f0759257139d15c87a6351c85da4fe9993684a598d6fbb0768` | 56 |

The lifecycle returns its pinned rendered ReasoningBank memory text, while C7
persists the top-1 selection but returns only the raw memory body.  Thus C7
does not establish that the provenance-bound retrieval is the same text that
the production executor receives.  This is an implementation/integration
defect, not a result about task performance or ReasoningBank.

The frozen manifest is
`df13823405b689e611dafa6e6e468ef9a79e895eead17d559ce7db94e8779376`; C8 is
`5d14f4eea0ba401c5dfbbec847ef12bf30e19244`; and the exposed-allocation
publication P8 is `5da504b6e902be32606d6e9e3812f66cdee2e0ec`.  They remain
read-only pre-dispatch evidence.  A successor must repair and test exact
callback-byte provenance before freezing a new manifest.
