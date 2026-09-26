"""Persistent JSON-lines native AppWorld worker for the registered smoke."""
import json, os, sys
from appworld import AppWorld

world=None
task_id=None
for line in sys.stdin:
    req=json.loads(line)
    op=req.get("op")
    if op=="start":
        allowed=set(filter(None, os.environ.get("APPWORLD_ALLOWED_TASKS", "50e1ac9_1,50e1ac9_2,fac291d_1").split(",")))
        if req.get("fixture") is True: allowed={"82e2fac_1"}
        if world is not None or req.get("task_id") not in allowed:
            raise ValueError("registered task required and only one world allowed")
        task_id=req["task_id"]
        fixture_mode = req.get("fixture") is True
        world=AppWorld(task_id=task_id,experiment_name=req["experiment_name"],raise_on_failure=False,timeout_seconds=30,raise_on_unsafe_syntax=True,null_patch_unsafe_execution=True,
                       **({"ground_truth_mode":"full", "load_ground_truth":True} if fixture_mode else {}))
        print(json.dumps({"ok":True,"task_id":task_id,"instruction":world.task.instruction,
                          "app_descriptions":world.task.app_descriptions}),flush=True)
    elif op=="action":
        if world is None: raise RuntimeError("start required")
        print(json.dumps({"ok":True,"output":world.execute(req["code"]),"completed":world.task_completed()}),flush=True)
    elif op=="finish":
        if world is None: raise RuntimeError("start required")
        if req.get("fixture_solution") is True and task_id=="82e2fac_1":
            world.execute(world.task.ground_truth.compiled_solution_code+"\nsolution(apis, requester)")
        score=world.evaluate()
        world.close()
        print(json.dumps({"ok":True,"task_id":task_id,"success":score.success,"pass_count":score.pass_count,"fail_count":score.fail_count,"num_tests":score.num_tests}),flush=True)
        break
    else: raise ValueError("unknown op")
