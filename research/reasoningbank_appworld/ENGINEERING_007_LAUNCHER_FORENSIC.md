# Engineering 007 launcher forensic and Engineering 008 allocation disposition

Engineering 007 is immutable and had a zero-dispatch launcher failure.  Its
manifest is `5a2266542a1b7006b2565ec486f16e6c1cf859b576499ad8de22ebab2568bcac`.
Read-only reconciliation found no ledger, scored artifact, retrieval record,
provider request, AppWorld execution, scorer invocation, or active runner.
Its only terminal condition was the pre-dispatch absence of
`OPENROUTER_API_KEY` in the detached child process.

The repair adds a WSL-only launcher boundary.  It requires the existing
protected environment file to be named by the process-local, absolute
`REASONINGBANK_PROTECTED_ENV_FILE` variable; sources it in the foreground WSL
process; exports `OPENROUTER_API_KEY`; and `exec`s Python without an additional
shell or background-child inheritance boundary.  It never records or displays
the credential or its value-derived material.

Engineering 007's allocation is also invalid for a fresh successor because it
reused the Engineering 001 public triple.  The Engineering 008 public-only
screening recorded in `engineering-008-fresh-allocation-no-go.json` therefore
uses execution/scoring evidence from the external E-backed artifact root and
explicitly excludes all previously frozen ReasoningBank engineering triples.
It found no eligible public development A/B/N triple.  This is a custody and
inventory NO-GO, not a method or outcome result.  No payload was opened and no
provider, model, embedding, AppWorld, scorer, or lifecycle call occurred.
