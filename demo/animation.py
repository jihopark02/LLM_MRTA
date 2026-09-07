"""Deterministic checkpoint-segment playback specs (§20, D-046).

The simulator has already committed the ``after`` checkpoint before anything
here runs.  This module only reconstructs a kinematic view of the recorded
schedule: UAVs interpolate on straight legs, UGVs along the Dijkstra path, and
agents stay at the target during dwell.  It neither advances execution nor
calls allocation, and it deliberately has no matplotlib dependency.
"""

import math
from dataclasses import dataclass, replace

from allocation.travel import start_ref, task_ref
from core.enums import PlatformKind
from demo.visualization import MapRenderSpec, runtime_map_spec
from execution.executor import ExecutionCheckpoint, SimExecutor
from scenarios.scene import Scene


@dataclass(frozen=True, slots=True)
class AgentFrameSpec:
    agent_id: str
    position: tuple[float, float]
    activity: str                 # IDLE | TRAVEL | DWELL
    task_id: str | None


@dataclass(frozen=True, slots=True)
class AnimationFrameSpec:
    simulation_time: float
    progress: float
    agents: tuple[AgentFrameSpec, ...]
    map_spec: MapRenderSpec


@dataclass(frozen=True, slots=True)
class PlaybackSpec:
    start_time: float
    end_time: float
    frames: tuple[AnimationFrameSpec, ...]


def _point(ref, scene: Scene) -> tuple[float, float]:
    if isinstance(ref, str):
        return tuple(map(float, scene.route_graph.position(ref)))
    return (float(ref[0]), float(ref[1]))


def _linear(
    start: tuple[float, float], end: tuple[float, float], progress: float
) -> tuple[float, float]:
    return (
        start[0] + (end[0] - start[0]) * progress,
        start[1] + (end[1] - start[1]) * progress,
    )


def _ugv_position(
    scene: Scene,
    start_node: str,
    end_node: str,
    progress: float,
) -> tuple[float, float]:
    """Distance-based position on the exact shortest path used by travel cost."""
    nodes = scene.route_graph.shortest_path_nodes(start_node, end_node)
    if nodes is None:
        raise ValueError(f"unreachable UGV playback leg: {start_node}->{end_node}")
    if len(nodes) == 1:
        return _point(nodes[0], scene)
    weights = [
        scene.route_graph.lane_weight(a, b)
        for a, b in zip(nodes, nodes[1:], strict=False)
    ]
    total = sum(weights)
    wanted = min(max(progress, 0.0), 1.0) * total
    walked = 0.0
    for a, b, weight in zip(nodes, nodes[1:], weights, strict=False):
        if wanted <= walked + weight:
            local = (wanted - walked) / weight
            return _linear(_point(a, scene), _point(b, scene), local)
        walked += weight
    return _point(nodes[-1], scene)


def _task_routes(checkpoint: ExecutionCheckpoint, scene: Scene):
    """task -> (agent, origin ref, target ref), reconstructed from departures."""
    work = checkpoint._work
    graph = work.graph
    assignments = dict(checkpoint.assignments)
    departures = dict(checkpoint.task_departure)
    routes = {}
    for agent_id in sorted(work.agents):
        agent = work.agents[agent_id]
        scene_agent = next(item for item in scene.fleet if item.agent_id == agent_id)
        current = start_ref(scene_agent, scene)
        task_ids = sorted(
            (
                task_id
                for task_id, owner in assignments.items()
                if owner == agent_id and task_id in departures
            ),
            key=lambda task_id: (departures[task_id], task_id),
        )
        for task_id in task_ids:
            destination = task_ref(agent, graph[task_id], scene)
            routes[task_id] = (agent_id, current, destination)
            current = destination
    return routes


def _finish_times(checkpoint: ExecutionCheckpoint) -> dict[str, float]:
    finish = dict(checkpoint.task_completion)
    for _, sim in checkpoint.sim:
        if sim.current is not None:
            finish[sim.current] = sim.finish_at
    return finish


def _agent_at(
    agent_id: str,
    when: float,
    checkpoint: ExecutionCheckpoint,
    scene: Scene,
    routes,
) -> AgentFrameSpec:
    work = checkpoint._work
    agent = work.agents[agent_id]
    departure = dict(checkpoint.task_departure)
    starts = dict(checkpoint.task_start)
    finish = _finish_times(checkpoint)
    owned = sorted(
        (task_id for task_id, route in routes.items() if route[0] == agent_id),
        key=lambda task_id: (departure[task_id], task_id),
    )

    scene_agent = next(a for a in scene.fleet if a.agent_id == agent_id)
    position = _point(start_ref(scene_agent, scene), scene)
    for task_id in owned:
        dep = departure[task_id]
        start = starts[task_id]
        end = finish[task_id]
        _, origin, target = routes[task_id]
        target_point = _point(target, scene)
        if when < dep:
            break
        if dep <= when < start:
            fraction = 1.0 if start == dep else (when - dep) / (start - dep)
            if agent.platform_kind is PlatformKind.UAV:
                position = _linear(_point(origin, scene), target_point, fraction)
            else:
                position = _ugv_position(scene, origin, target, fraction)
            return AgentFrameSpec(agent_id, position, "TRAVEL", task_id)
        position = target_point
        if start <= when < end:
            return AgentFrameSpec(agent_id, position, "DWELL", task_id)
    return AgentFrameSpec(agent_id, position, "IDLE", None)


def _frame_map(
    base: MapRenderSpec,
    frame_agents: tuple[AgentFrameSpec, ...],
    when: float,
    departure: dict[str, float],
    completion: dict[str, float],
) -> MapRenderSpec:
    position_of = {item.agent_id: item.position for item in frame_agents}
    agents = tuple(
        replace(agent, position=position_of[agent.agent_id]) for agent in base.agents
    )
    legs = tuple(
        replace(
            leg,
            phase=(
                "completed"
                if completion.get(leg.task_id, math.inf) <= when
                else "in_progress"
                if departure.get(leg.task_id, math.inf) <= when
                else "remaining"
            ),
        )
        for leg in base.legs
    )
    return replace(
        base,
        mode="playback",
        agents=agents,
        legs=legs,
        simulation_time=when,
    )


def build_playback_spec(
    scene: Scene,
    before: ExecutionCheckpoint,
    after: ExecutionCheckpoint,
    *,
    frame_count: int = 18,
) -> PlaybackSpec:
    """Interpolate one already-committed checkpoint segment.

    ``before`` and ``after`` remain frozen.  The latter contains the complete
    timing information for every agent that moved or dwelled in this segment.
    """
    if not isinstance(frame_count, int) or isinstance(frame_count, bool) or frame_count < 2:
        raise ValueError("frame_count must be an integer >= 2")
    if not math.isfinite(before.now) or not math.isfinite(after.now):
        raise ValueError("checkpoint times must be finite")
    if after.now <= before.now:
        raise ValueError("after checkpoint must be later than before checkpoint")
    if set(before._work.agents) != set(after._work.agents):
        raise ValueError("checkpoint agent sets differ")

    runtime = SimExecutor.from_checkpoint(after, scene)
    base = runtime_map_spec(scene, runtime)
    routes = _task_routes(after, scene)
    departure = dict(after.task_departure)
    completion = dict(after.task_completion)
    frames = []
    duration = after.now - before.now
    for index in range(frame_count):
        progress = index / (frame_count - 1)
        when = before.now + duration * progress
        agents = tuple(
            _agent_at(agent_id, when, after, scene, routes)
            for agent_id in sorted(after._work.agents)
        )
        frames.append(
            AnimationFrameSpec(
                simulation_time=when,
                progress=progress,
                agents=agents,
                map_spec=_frame_map(base, agents, when, departure, completion),
            )
        )
    return PlaybackSpec(before.now, after.now, tuple(frames))


__all__ = [
    "AgentFrameSpec",
    "AnimationFrameSpec",
    "PlaybackSpec",
    "build_playback_spec",
]
