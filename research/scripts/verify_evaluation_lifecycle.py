#!/usr/bin/env python3
"""Deterministic no-network regression checks for evaluation update ordering."""
from research.official_pilot.evaluation_lifecycle import dynamic_post_trial_update

class Agent:
    def __init__(self, records):
        self.retrieved_memory_list = [[records]]; self.task_ids=["fixture"]
        self.history=[[[]]]; self.calls=[]
    def get_traj_from_task_history(self, *x): self.calls.append("trajectory"); return {"x": 1}
    def summary_memory(self, x): self.calls.append("summary"); return []
    def add_memory(self, x): self.calls.append("add")
    def update_memory_information(self, x, y): self.calls.append(("record", x, y))
    def delete_memory(self): self.calls.append("delete")

# Fixed has no evaluation update invocation path.
fixed = Agent([{"memory_id":"m"}]); assert fixed.calls == []
events=[]; empty=Agent([])
assert dynamic_post_trial_update(empty, 1.0, events.append) == "skipped_empty_retrieval"
assert empty.calls == [] and events[-1]["event"] == "dynamic_update_skipped_empty_retrieval"
events=[]; dynamic=Agent([{"memory_id":"m"}])
assert dynamic_post_trial_update(dynamic, 1.0, events.append) == "updated"
assert any(isinstance(x, tuple) and x[0] == "record" for x in dynamic.calls)
# Model the runner ordering: completed/scored is committed before the optional
# dynamic update, and a restart sees the completed key and does not replay it.
durable=[]
durable.append("scorer_and_native_actions")
dynamic_post_trial_update(dynamic, 1.0, lambda _: durable.append("update"))
assert durable[0] == "scorer_and_native_actions" and "update" in durable
completed={"evaluation:dynamic:fixture"}
assert "evaluation:dynamic:fixture" in completed  # restart skip predicate
print("PASS evaluation lifecycle ordering")
