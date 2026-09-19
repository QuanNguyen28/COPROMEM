"""DecompositionSchema: Persistent first-class structural memory object for task factorizations."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from .contracts import Contract
from .types import DependencyEdge, SubtaskNode, as_jsonable


@dataclass(frozen=True)
class DecompositionSchema:
    """A persistent, learned task decomposition schema represented as a validated DAG."""

    schema_id: str
    task_family: str
    semantic_cues: tuple[str, ...]
    nodes: tuple[SubtaskNode, ...]
    edges: tuple[DependencyEdge, ...]
    preconditions: tuple[str, ...] = ()
    contracts: tuple[Contract, ...] = ()
    structural_stats: dict[str, Any] = field(default_factory=dict)
    status: str = "candidate"

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Validate node uniqueness, edge reference integrity, and acyclicity."""
        node_ids = set()
        for node in self.nodes:
            if node.node_id in node_ids:
                raise ValueError(f"Duplicate node_id '{node.node_id}' in schema '{self.schema_id}'")
            node_ids.add(node.node_id)

        for edge in self.edges:
            if edge.source_node not in node_ids:
                raise ValueError(
                    f"Edge source '{edge.source_node}' not found in nodes of schema '{self.schema_id}'"
                )
            if edge.target_node not in node_ids:
                raise ValueError(
                    f"Edge target '{edge.target_node}' not found in nodes of schema '{self.schema_id}'"
                )
            if edge.source_node == edge.target_node:
                raise ValueError(
                    f"Self-loop detected on node '{edge.source_node}' in schema '{self.schema_id}'"
                )

        # Check for cycles via topological sort
        self.topological_sort()

    def topological_sort(self) -> list[SubtaskNode]:
        """Return nodes in valid execution order using Kahn's algorithm."""
        in_degree: dict[str, int] = {node.node_id: 0 for node in self.nodes}
        adj: dict[str, list[str]] = defaultdict(list)
        node_map = {node.node_id: node for node in self.nodes}

        for edge in self.edges:
            adj[edge.source_node].append(edge.target_node)
            in_degree[edge.target_node] += 1

        queue = deque([node_id for node_id, deg in in_degree.items() if deg == 0])
        ordered: list[SubtaskNode] = []

        while queue:
            curr = queue.popleft()
            ordered.append(node_map[curr])
            for neighbor in adj[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(ordered) != len(self.nodes):
            raise ValueError(f"Cycle detected in decomposition DAG for schema '{self.schema_id}'")

        return ordered

    def parallel_waves(self) -> list[list[SubtaskNode]]:
        """Compute execution waves (groups of subtasks that can run concurrently)."""
        node_map = {node.node_id: node for node in self.nodes}
        adj: dict[str, list[str]] = defaultdict(list)
        in_degree: dict[str, int] = {node.node_id: 0 for node in self.nodes}

        for edge in self.edges:
            adj[edge.source_node].append(edge.target_node)
            in_degree[edge.target_node] += 1

        current_wave = [nid for nid, deg in in_degree.items() if deg == 0]
        waves: list[list[SubtaskNode]] = []

        while current_wave:
            waves.append([node_map[nid] for nid in current_wave])
            next_wave: list[str] = []
            for nid in current_wave:
                for neighbor in adj[nid]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        next_wave.append(neighbor)
            current_wave = next_wave

        return waves

    def get_contract_for_edge(self, source: str, target: str) -> Contract | None:
        """Find the contract assigned to a directed edge between two nodes."""
        edge = next(
            (e for e in self.edges if e.source_node == source and e.target_node == target),
            None,
        )
        if not edge or not edge.contract_id:
            return None
        return next((c for c in self.contracts if c.contract_id == edge.contract_id), None)

    @property
    def transfer_reliability(self) -> float:
        return float(self.structural_stats.get("transfer_reliability", 0.0))

    @property
    def execution_count(self) -> int:
        return int(self.structural_stats.get("execution_count", 0))

    def admitted(self) -> DecompositionSchema:
        return replace(self, status="admitted")

    def with_stats(self, **stats: Any) -> DecompositionSchema:
        merged = dict(self.structural_stats)
        merged.update(stats)
        return replace(self, structural_stats=merged)

    def as_dict(self) -> dict[str, Any]:
        return as_jsonable(asdict(self))
