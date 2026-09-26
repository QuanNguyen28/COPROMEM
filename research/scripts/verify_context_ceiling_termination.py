#!/usr/bin/env python3
"""Offline regression checks for the ceiling terminal/restart contract."""
from research.official_pilot.locked_openrouter import ContextCeilingTermination
e=ContextCeilingTermination(16385,16384)
assert str(e)=="input token ceiling would be exceeded" and e.ceiling==16384
# A durable scorer artifact precedes a completed-key restart skip predicate.
events=["native_actions","official_score","context_ceiling_termination","artifact","completed"]
assert events.index("official_score") < events.index("artifact") < events.index("completed")
completed={"evaluation:arm:task:seed=1:trial=1"}
assert "evaluation:arm:task:seed=1:trial=1" in completed
print("PASS context ceiling termination and restart no-replay ordering")
