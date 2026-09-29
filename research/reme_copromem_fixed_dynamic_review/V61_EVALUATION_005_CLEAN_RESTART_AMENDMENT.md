# Evaluation 005 clean-restart amendment

Evaluation 005 is a clean, exploratory, compatibility-conditioned restart
after evaluation 004's infrastructure interruption.  It reuses the frozen six
task IDs, five arms, seeds, model route, action cap, scorer, and initial bank
identities, but starts at 0/60 and imports no evaluation-004 artifact or state.

The only changes are infrastructure: the versioned scored-artifact evidence
contract, its shared producer/consumer validation, and explicit accounting for
the predecessor's settled and unresolved historical exposure.  It does not
change method behavior or scientific settings.

The carried historical amount is USD `2.36387062`: USD `2.35384537` prior
historical settled exposure, USD `0.00401745` settled evaluation-004 exposure,
and USD `0.00600780` retained maximum for the unresolved predecessor request.
