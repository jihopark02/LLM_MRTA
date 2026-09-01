"""Platform-aware travel cost (RESEARCH_CONTRACT.md §8).

UAV legs are Euclidean distance / speed. UGV legs are the route-graph Dijkstra
shortest-path distance / speed, between named access nodes — never raw
coordinates. A UGV's start node comes from ``scene.agent_access_nodes`` (contract
§6 keeps route nodes off the core Agent); a UGV task's node is the target
incident's ``access_node``.

This is NOT ported from LLM_CBBA — that repo's travel is a single Euclidean
formula. Only the CBBA/scoring structure is reused (see docs/PROVENANCE.md).
"""

import math

from core.agent import Agent
from core.enums import PlatformKind
from core.task import Task
from scenarios.scene import Scene

# A leg reference is either a 2D position (UAV) or a route-node id (UGV).
LegRef = tuple[float, float] | str


class UnreachableError(RuntimeError):
    def __init__(self, agent_id: str, target: str) -> None:
        super().__init__(f"{agent_id} cannot reach {target} on the route graph")


def start_ref(agent: Agent, scene: Scene) -> LegRef:
    if agent.platform_kind is PlatformKind.UAV:
        return agent.position
    return scene.agent_access_nodes[agent.agent_id]


def task_ref(agent: Agent, task: Task, scene: Scene) -> LegRef:
    if agent.platform_kind is PlatformKind.UAV:
        return task.position
    return scene.incidents[task.target].access_node


def leg_time(agent: Agent, from_ref: LegRef, task: Task, scene: Scene) -> float:
    """Seconds to move ``agent`` from ``from_ref`` to ``task``."""
    if agent.platform_kind is PlatformKind.UAV:
        return math.dist(from_ref, task.position) / agent.speed
    to_node = scene.incidents[task.target].access_node
    dist = scene.route_graph.shortest_path_distance(from_ref, to_node)
    if dist is None:
        raise UnreachableError(agent.agent_id, task.task_id)
    return dist / agent.speed
