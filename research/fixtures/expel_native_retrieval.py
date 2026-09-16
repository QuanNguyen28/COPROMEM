"""Authored offline fixture invoking ExpeL's unmodified retrieval methods.

This bypasses environment/LLM initialization, not retrieval. The word-count budget
is a fixture stub, not ExpeL's production tokenizer or a reproduced benchmark.
"""

import json
from functools import partial
from types import SimpleNamespace

import numpy as np
import torch
from agent.expel import ExpelAgent
from memory import EMBEDDERS, Trajectory
from prompts import CYCLER, STEP_CYCLER, STEP_IDENTIFIER, STEP_STRIPPER

torch.set_num_threads(2)
torch.manual_seed(0)
np.random.seed(0)
embedder = EMBEDDERS("huggingface")(model_name="/model", model_kwargs={"device": "cpu"})
query = "Question: How do I renew an expired library card?"
related = "Question: How can I renew my library membership?"
long_task = "Question: What is required to renew an expired library card?"
unrelated = "Question: How do I bake a chocolate cake?"

vector = np.array(embedder.embed_query(query))
repeated = np.array(embedder.embed_query(query))
assert vector.shape == (768,) and np.isfinite(vector).all()
assert np.allclose(vector, repeated, rtol=0, atol=1e-6)

agent = object.__new__(ExpelAgent)
agent.benchmark_name = "hotpotqa"  # Native formatting only; no HotpotQA examples.
agent.env = SimpleNamespace(env_name="hotpotqa")
agent._train = False
agent.testing = False
agent.fewshot_strategy = "task_similarity"
agent.reranker = "none"
agent.buffer_retrieve_ratio = 4
agent.num_fewshots = 1
agent.max_fewshot_tokens = 60
agent.token_counter = lambda text: len(text.split())  # Explicit budget-test stub.
agent.embedder = embedder
agent.message_splitter = CYCLER["hotpotqa"]
agent.identifier = STEP_IDENTIFIER["hotpotqa"]
agent.message_step_splitter = partial(STEP_CYCLER, "hotpotqa")
agent.step_stripper = STEP_STRIPPER["hotpotqa"]
agent.all_fewshots = []
agent.fewshots = []
agent.prompt_history = []
agent.task = query


def trajectory(task, content):
    return Trajectory(
        task=task,
        trajectory=content,
        reflections=[],
        splitter=agent.message_splitter,
        identifier=agent.identifier,
        step_splitter=agent.message_step_splitter,
    )


short_related = (
    "Thought 1: Check the membership renewal procedure.\n"
    "Action 1: Search[library renewal]\n"
    "Observation 1: Bring the expired card to the desk."
)
agent.succeeded_trial_history = {
    query: [trajectory(query, "Action 1: Finish[self-match must be excluded]")],
    related: [
        trajectory(related, short_related + "\nThought 2: " + "detail " * 90),
        trajectory(related, short_related),
    ],
    long_task: [trajectory(long_task, "Thought 1: " + "detail " * 100)],
    unrelated: [trajectory(unrelated, "Action 1: Search[chocolate cake recipe]")],
}

# Actual upstream setup_vectorstore, environment/type filtering, FAISS embedding,
# top-k, shortest-trajectory choice, budget filtering and self-task exclusion.
agent.update_dynamic_prompt_components()
selected = list(agent.fewshots)
assert selected == [related + "\n" + short_related], selected
ranking = [
    {"task": doc.metadata["task"], "squared_l2": float(score)}
    for doc, score in agent.vectorstore.similarity_search_with_score(query, k=4)
]
assert ranking[0]["task"] == query and ranking[0]["squared_l2"] < 1e-8
assert agent.vectorstore.index.ntotal == 4
assert all(
    doc.metadata["type"] == "task" and doc.metadata["env_name"] == "hotpotqa"
    for doc in agent.vectorstore.docstore._dict.values()
)

agent.update_dynamic_prompt_components()
assert agent.fewshots == selected
agent.max_fewshot_tokens = 1
agent.update_dynamic_prompt_components()
assert agent.fewshots == []

print(
    json.dumps(
        {
            "kind": "authored native retrieval component fixture, not benchmark performance",
            "passed_checks": [
                "local checkpoint produces finite 768-dimensional vectors",
                "repeated CPU embeddings match within absolute tolerance 1e-6",
                "native setup and FAISS task/environment filter index four task documents",
                "nearest self-task ranks first but is excluded from fewshots",
                "over-budget trajectory is excluded and shortest related trajectory is selected",
                "repeated native retrieval preserves selected fewshot",
                "one-word fixture budget excludes all trajectories",
            ],
            "initial_ranking": ranking,
            "selected_fewshots": selected,
            "embedding_class": type(embedder).__name__,
            "embedding_model_max_seq_length": embedder.client.max_seq_length,
            "embedding_dimension": int(vector.shape[0]),
            "paid_model_calls": 0,
            "local_embedding_inference": True,
            "limitations": [
                "Authored histories are not environment-success trajectories or learned rules.",
                "Environment and LLM constructors are bypassed using a controlled native instance.",
                "Word-count budget stub, not the production tokenizer.",
                "No native rollout, insight generation, held-out retrieval score or AppWorld adaptation.",
            ],
        }
    )
)
