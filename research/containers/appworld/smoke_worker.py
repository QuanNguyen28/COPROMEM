"""JSON-lines WSL AppWorld worker for the registered plumbing smoke."""
from __future__ import annotations
import json, sys
REGISTERED = {"50e1ac9_1", "50e1ac9_2", "fac291d_1"}
def dry_run(task_ids, inventory):
    unknown = set(task_ids) - REGISTERED
    if unknown or not set(task_ids).issubset(set(inventory)):
        raise ValueError("unregistered or unavailable task ID")
    return {"mode":"dry_run","task_ids":list(task_ids),"payload_opened":False}
def fixture(world, actions):
    outputs=[]
    for action in actions: outputs.append(world.execute(action))
    return {"mode":"fixture","outputs":outputs,"score":world.score(),"terminated":True}
def native_fixture():
    from appworld import AppWorld
    with AppWorld(task_id="82e2fac_1", experiment_name="worker_fixture",
                  ground_truth_mode="full", load_ground_truth=True,
                  raise_on_failure=False, timeout_seconds=15,
                  raise_on_unsafe_syntax=True, null_patch_unsafe_execution=True) as world:
        # Two harmless public Python actions establish persistent interpreter state.
        first=world.execute("worker_counter = 1")
        second=world.execute("worker_counter = worker_counter + 1")
        solved=world.execute(world.task.ground_truth.compiled_solution_code+"\nsolution(apis, requester)")
        score=world.evaluate()
        return {"task_id":"82e2fac_1","actions":[first,second,solved],
                "persistent_state_actions":2,"terminated":True,
                "pass_count":score.pass_count,"fail_count":score.fail_count,
                "num_tests":score.num_tests,"success":score.success,"model_calls":0}
def main():
    request=json.loads(sys.stdin.readline())
    if request["mode"]=="dry_run":
        from appworld import load_task_ids
        print(json.dumps(dry_run(request["task_ids"], load_task_ids("train"))))
        return
    raise RuntimeError("live task execution requires the parent registered runner")
if __name__=="__main__": main()
