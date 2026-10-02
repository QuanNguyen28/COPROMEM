# v6.2.2 Real Pilot 100 — Recovery 002

Publication identity for the recovery successor of the immutable
`v6_2_2_real_pilot_100_001` infrastructure failure.

- Executable source commit (C): `5e32ca33c9dbe320ac8bcee107af11ca87306946`
- Frozen successor manifest SHA-256:
  `629a469d6db87a9f206457073d3c813f3e7809acbeb9135681cd697567f0738e`
- Predecessor manifest SHA-256:
  `4b8a8253c1f12ca817568f0a7f909cd3713a116a180e279eda6f9fa047720997`
- Imported prefix: exactly nine scored trajectories.
- Rule: predecessor artifacts, journals, scorer records, ledger and ReMe
  Dynamic checkpoints remain immutable; no predecessor provider call is replayed.

The successor has the same frozen 100-task, six-arm, three-trial schedule.
ReasoningBank query embeddings are an explicitly registered and budgeted role
(`reasoningbank_embedding`), so the successor cannot fail with an unregistered
provider-call role at its first ReasoningBank retrieval.
