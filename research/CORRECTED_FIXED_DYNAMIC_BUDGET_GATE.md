# Corrected fixed/dynamic pilot budget gate

The registered 32,768 input-token and 2,048 completion-token ceilings cost
USD 0.012288 per generative request at the locked USD 0.30/M input and USD
1.20/M completion tariff. The 24-task target costs USD 185.794560 in executor
requests alone and cannot fit the USD 140 cap.

The protocol is therefore symmetrically reduced to the permitted 16-task
minimum: 12 × 2 × 30 acquisition executor calls and 16 × 4 × 5 × 30
evaluation executor calls cost USD 126.812160. The registered upper bounds
for 320 CoProMem decomposition calls, 24 ReMe initial-bank calls, 64 dynamic
summaries, two minimal canaries, and 216 embeddings yield USD 131.991797.
The USD 140 ledger remains fail-closed; no expected early termination is used
to justify the gate.
