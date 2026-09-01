"""Deterministic task compiler (RESEARCH_CONTRACT.md §7).

The LLM emits only ``task_type`` + ``target`` + ``priority``. This module
resolves everything else — ``task_id``, ``position``, ``required_capabilities``,
``eligible_platforms``, ``duration`` — from the semantic scene and a fixed
default table, so there is a single source of truth for coordinates.

The same compiler is used for the hand-authored P1 reference fixture and for
LLM output in P5.
"""

from dataclasses import dataclass

from core.enums import Capability, PlatformKind, TaskStatus, TaskType
from core.task import Task
from core.task_graph import TaskGraph
from scenarios.scene import Scene

__all__ = ["TASK_TABLE", "TaskSpec", "compile_task", "compile_graph", "task_id_for"]

UAV = frozenset({PlatformKind.UAV})
UGV = frozenset({PlatformKind.UGV})


@dataclass(frozen=True, slots=True)
class TaskSpec:
    required_capabilities: frozenset[Capability]
    eligible_platforms: frozenset[PlatformKind]
    duration: float
    target_kind: str  # "zone" or "incident"


# Fixed default table (contract §4 completion semantics, §5 eligible bidders).
# Durations are dwell times in seconds; tunable, not a contract-fixed value.
TASK_TABLE: dict[TaskType, TaskSpec] = {
    TaskType.AREA_RECON: TaskSpec(
        frozenset({Capability.AERIAL_RECON}), UAV, 40.0, "zone"
    ),
    TaskType.THERMAL_RECON: TaskSpec(
        frozenset({Capability.THERMAL_SENSOR}), UAV, 30.0, "incident"
    ),
    TaskType.SUPPRESSANT_DROP: TaskSpec(
        frozenset({Capability.SUPPRESSANT_PAYLOAD}), UAV, 25.0, "incident"
    ),
    TaskType.GROUND_INSPECTION: TaskSpec(
        frozenset({Capability.GROUND_MOBILITY}), UGV, 35.0, "incident"
    ),
    TaskType.HAZARD_MARKER_DEPLOY: TaskSpec(
        frozenset({Capability.GROUND_MOBILITY, Capability.MARKER_DISPENSER}),
        UGV,
        20.0,
        "incident",
    ),
}


def task_id_for(task_type: TaskType, target: str) -> str:
    return f"{task_type.value}__{target}"


def _resolve_position(scene: Scene, spec: TaskSpec, task_type: TaskType, target: str):
    if spec.target_kind == "zone":
        if target not in scene.zones:
            raise ValueError(f"{task_type.value}: unknown zone target {target}")
        return scene.zones[target].recon_waypoint
    if target not in scene.incidents:
        raise ValueError(f"{task_type.value}: unknown incident target {target}")
    incident = scene.incidents[target]
    if task_type in (TaskType.GROUND_INSPECTION, TaskType.HAZARD_MARKER_DEPLOY):
        # UGV moves to the incident's ground access point (contract §4).
        return scene.route_graph.position(incident.access_node)
    return incident.position


def compile_task(scene: Scene, task_type: TaskType, target: str, priority: int) -> Task:
    spec = TASK_TABLE[task_type]
    return Task(
        task_id=task_id_for(task_type, target),
        task_type=task_type,
        target=target,
        position=_resolve_position(scene, spec, task_type, target),
        priority=int(priority),
        required_capabilities=spec.required_capabilities,
        eligible_platforms=spec.eligible_platforms,
        duration=spec.duration,
        status=TaskStatus.PENDING,
    )


def compile_graph(
    scene: Scene,
    task_specs: list[tuple[TaskType, str, int]],
    edges: list[tuple[tuple[TaskType, str], tuple[TaskType, str]]],
) -> TaskGraph:
    """Build a TaskGraph from (type, target, priority) tuples and (type,target)
    edge endpoints. Status is set to PENDING then recomputed to the READY frontier.
    """
    graph = TaskGraph()
    for task_type, target, priority in task_specs:
        graph.add_task(compile_task(scene, task_type, target, priority))
    for (pt, ptgt), (st, stgt) in edges:
        graph.add_edge(task_id_for(pt, ptgt), task_id_for(st, stgt))
    graph.recompute_ready()
    return graph
