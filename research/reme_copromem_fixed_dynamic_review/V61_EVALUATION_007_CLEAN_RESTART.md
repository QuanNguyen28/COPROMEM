# Evaluation 007 clean restart

`v6_1_exploratory_diagnostic_evaluation_007_clean_restart` is a separately
frozen exploratory diagnostic run.  It begins at 0/60 and uses the six already
frozen development task IDs, five arms, and two seeds without task selection or
substitution.  Evaluation 006 remains immutable audit-only evidence: its
fourteen artifacts and all predecessor Dynamic states are excluded from both
analysis and continuation.

The frozen manifest SHA-256 is
`5b0520f6871a495a6a27f0003642533503788eb53edc88dbed72861cf325577a` and
its source commit is `f0bd1dd203589714a5a2d9c3ffdf557991464f1a`.

The only infrastructure amendment is the canonical zero-action execution
evidence branch.  It accepts a zero-byte telemetry journal solely for a
settled 2,048-token `length` response with no tool call or submitted action,
and with a cryptographically bound official score, terminal-output hash,
settlement, progress event, manifest, and source commit.  Ordinary empty
journals remain invalid.  Initial ReMe and CoProMem bank identities and the
scientific design are unchanged.
