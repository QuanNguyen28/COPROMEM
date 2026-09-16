"""Native environment smoke, not a learned/model-backed or solved rollout."""

import hashlib
import json
import os
import random
from pathlib import Path

import numpy as np
from alfworld.info import ALFRED_PDDL_PATH, ALFRED_TWL2_PATH
from envs.alfworld.alfworld import AlfworldEnv
from omegaconf import OmegaConf

random.seed(42)
np.random.seed(42)
logic = {}
for installed, name in (
    (ALFRED_PDDL_PATH, "alfred.pddl"),
    (ALFRED_TWL2_PATH, "alfred.twl2"),
):
    package_hash = hashlib.sha256(Path(installed).read_bytes()).hexdigest()
    selected_hash = hashlib.sha256(
        (Path("/dataset/logic") / name).read_bytes()
    ).hexdigest()
    assert package_hash == selected_hash, (
        name,
        "pinned source differs from installed package",
    )
    logic[name] = package_hash

config = OmegaConf.load("/vendor/configs/benchmark/alfworld.yaml")
config.split = "eval_out_of_distribution"  # Native eval wrapper; train fixture data.
config.dataset.eval_ood_data_path = "/dataset/json_2.1.1/train"
config.dataset.data_path = "/dataset/json_2.1.1/train"
config.logic.domain = "/dataset/logic/alfred.pddl"
config.logic.grammar = "/dataset/logic/alfred.twl2"
config.general.use_cuda = False
gamefile = os.environ["ALFWORLD_FIXTURE_GAMEFILE"]
assert gamefile.startswith("/dataset/json_2.1.1/train/")

wrapper = AlfworldEnv(gamefile=gamefile, config=config, max_steps=20)
try:
    observations, info = wrapper.env.reset()
    assert isinstance(observations[0], str) and observations[0]
    assert not any(
        key in info for key in ("extra.expert_plan", "policy_commands", "facts")
    )
    rows = []
    for action in ("look", "inventory", "inventory"):
        observation, reward, terminated, truncated, step = wrapper.step(action)
        rows.append(
            {
                "action": action,
                "observation": observation,
                "reward": bool(reward),
                "terminated": bool(terminated),
                "truncated": bool(truncated),
                "next_step": step,
            }
        )
    assert not any(row["reward"] for row in rows)
    assert not rows[0]["terminated"] and not rows[1]["terminated"]
    assert rows[2]["terminated"]
    assert not wrapper.success_fn()
    print(
        "COPROMEM_ALFWORLD_NATIVE="
        + json.dumps(
            {
                "kind": "unmodified ExpeL native environment wrapper on one train fixture",
                "initial_public_observation": observations[0],
                "requested_information_keys": sorted(info),
                "expert_plan_exposed": False,
                "actions": rows,
                "native_success": bool(wrapper.success_fn()),
                "environment_family": wrapper.env_name,
                "logic_package_sha256": logic,
                "model_calls": 0,
                "limitations": [
                    "Predetermined neutral actions, not a learned or model-backed task-solving attempt.",
                    "Native evaluation wrapper mode points at one hash-selected train task.",
                    "Current default generated data and compatibility dependencies are disclosed adaptations.",
                    "No complete checkpoint, agent/insight reproduction or published-score claim.",
                ],
            }
        )
    )
finally:
    wrapper.env.close()
