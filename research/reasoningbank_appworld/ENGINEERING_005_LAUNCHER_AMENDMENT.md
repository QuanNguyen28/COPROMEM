# Engineering 005 launcher-only recovery amendment

Engineering 004 is immutable and remains a zero-dispatch infrastructure
failure.  Its detached non-interactive WSL launcher did not receive the already
configured `OPENROUTER_API_KEY`; it failed before creating a ledger, opening a
payload, starting a worker, or contacting any provider, AppWorld, or scorer.

Engineering 005 changes only the launch environment boundary.  The detached
WSL process sources the existing protected E-backed configuration file in its
own process environment before it invokes the immutable executable checkout.
The credential is never rendered, hashed, persisted, passed as a command-line
argument, included in a manifest, or committed.  A pre-dispatch check records
only a boolean presence result.

The scientific allocation, task-major schedule, arms, prompts, models,
temperatures, token/action limits, embedding route, empty initial ReasoningBank
state, Dynamic lifecycle, recovery-import evidence, USD 50 cap, and 5/4/3 GiB
storage policy are unchanged.  Engineering 001 through Engineering 004 remain
immutable.  Engineering 005 imports only the validated Engineering 002 No
Memory artifact by content-addressed reference and executes the remaining
eleven registered trajectories without copying or replaying predecessor work.
