# Corrected fixed/dynamic v2 budget gate

The v2 successor carries the immutable v1 exposure of USD 0.048008 and uses
eight new shared acquisition trajectories. The original 24-task evaluation is
already impossible at the frozen 32,768-input / 2,048-output ceilings, so the
permitted 16-task minimum is evaluated here.

At the locked USD 0.30/M input and USD 1.20/M completion tariff, one registered
generative maximum costs USD 0.012288. The conservative envelope includes 240
new acquisition executor calls, 9,600 evaluation executor calls, 320 CoProMem
decomposition calls, 96 ReMe summary/update calls, and 216 Azure embedding
calls. It also adds a 15% explicitly non-dispatchable contingency.

The all-inclusive v2 bound is USD 145.18108448, which exceeds the USD 140.00
hard cap even at the protocol's minimum 16 evaluation task IDs. Reducing the
evaluation set further, action limits, arm count, trial streams, or token
ceilings is prohibited. Consequently the v2 manifest is frozen as a
fail-closed budget preflight and no task payload or model call may be opened
under this cap.
