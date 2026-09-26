"""Authorized zero-model native AppWorld fixture; accepts only 82e2fac_1."""
import json
import sys
from appworld import AppWorld

if sys.argv[1:] != ["82e2fac_1"]:
    raise SystemExit("fixture is restricted to 82e2fac_1")
with AppWorld(task_id="82e2fac_1", experiment_name="fixture", ground_truth_mode="full",
              load_ground_truth=True, raise_on_failure=False, timeout_seconds=15,
              raise_on_unsafe_syntax=True, null_patch_unsafe_execution=True) as world:
    world.execute(world.task.ground_truth.compiled_solution_code + "\nsolution(apis, requester)")
    score = world.evaluate()
    print(json.dumps({"task_id":"82e2fac_1","success":score.success,"pass_count":score.pass_count,
                      "fail_count":score.fail_count,"num_tests":score.num_tests,"model_calls":0}))
