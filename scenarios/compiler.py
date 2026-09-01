"""Deterministic task compiler (RESEARCH_CONTRACT.md §7).

The LLM emits only ``task_type`` + ``target``. This module resolves everything
else — ``task_id``, ``position``, ``priority``, ``required_capabilities``,
``eligible_platforms``, ``duration`` — from the semantic scene and a fixed
default table, so there is a single source of truth for coordinates and
priority (D-022).

**Input boundary.** ``compile_reference_graph`` is for *trusted* task lists: the
hand-authored P1 reference fixture, and (P5) LLM output that has ALREADY passed
the P2 whole-graph Validator. It raises on structurally broken input (unknown
edge endpoint, duplicate edge) rather than silently dropping it. Raw LLM
candidates are validated by the P2 Validator on their own candidate
representation — where E_UNKNOWN_REF / E_DUPLICATE_EDGE are reported — before
they ever reach this compiler.
"""

import math
from dataclasses import dataclass

from core.enums import Capability, PlatformKind, TaskStatus, TaskType
from core.task import Task
from core.task_graph import TaskGraph
from scenarios.scene import Scene

__all__ = [
    "TASK_TABLE",
    "TaskSpec",
    "AREA_RECON_PRIORITY",
    "derive_priority",
    "compile_task",
    "compile_reference_graph",
    "task_id_for",
]

UAV = frozenset({PlatformKind.UAV})
UGV = frozenset({PlatformKind.UGV})

# AREA_RECON targets a zone, which carries no incident severity, so every zone
# survey gets the same priority — set below both incident priorities (7, 9) so
# CBBA puts an in-progress incident response ahead of routine zone recon
# (contract §7, D-022).
AREA_RECON_PRIORITY = 4


@dataclass(frozen=True, slots=True)
class TaskSpec:
    required_capabilities: frozenset[Capability]
    eligible_platforms: frozenset[PlatformKind]
    duration: float
    target_kind: str  # "zone" or "incident"


# Fixed default table (contract §4 completion semantics, §5 eligible bidders).
# Durations are symbolic dwell times in seconds — one fixed value per task_type,
# not a physical flight/suppression time (contract §4, D-016).
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
    TaskType.GROUND_SUPPRESSION: TaskSpec(
        frozenset({Capability.GROUND_MOBILITY, Capability.SUPPRESSANT_APPLICATOR}),
        UGV,
        45.0,  # symbolic; the culminating ground action (D-016)
        "incident",
    ),
}


assert set(TASK_TABLE) == set(TaskType), "TASK_TABLE must cover every TaskType"
assert all(
    math.isfinite(s.duration) and s.duration > 0.0 for s in TASK_TABLE.values()
), "TASK_TABLE durations must be finite and positive"


def task_id_for(task_type: TaskType, target: str) -> str:
    return f"{task_type.value}__{target}"


def derive_priority(scene: Scene, task_type: TaskType, target: str) -> int:
    """Priority is scene-derived, never LLM-supplied (contract §7, D-022):
    an incident task inherits its incident's priority; a zone survey gets the
    fixed AREA_RECON_PRIORITY."""
    if TASK_TABLE[task_type].target_kind == "incident":
        if target not in scene.incidents:
            raise ValueError(f"{task_type.value}: unknown incident target {target}")
        return scene.incidents[target].priority
    return AREA_RECON_PRIORITY


def _resolve_position(scene: Scene, spec: TaskSpec, task_type: TaskType, target: str):
    if spec.target_kind == "zone":
        if target not in scene.zones:
            raise ValueError(f"{task_type.value}: unknown zone target {target}")
        return scene.zones[target].recon_waypoint
    if target not in scene.incidents:
        raise ValueError(f"{task_type.value}: unknown incident target {target}")
    incident = scene.incidents[target]
    if task_type in (TaskType.GROUND_INSPECTION, TaskType.GROUND_SUPPRESSION):
        # UGV moves to the incident's ground access point (contract §4).
        return scene.route_graph.position(incident.access_node)
    return incident.position


def compile_task(scene: Scene, task_type: TaskType, target: str, priority: int) -> Task:
    spec = TASK_TABLE[task_type]
    # priority is passed through unchanged — Task.__post_init__ enforces int 1..10
    # (contract §7). Coercing here would let a bad fixture value slip past.
    return Task(
        task_id=task_id_for(task_type, target),
        task_type=task_type,
        target=target,
        position=_resolve_position(scene, spec, task_type, target),
        priority=priority,
        required_capabilities=spec.required_capabilities,
        eligible_platforms=spec.eligible_platforms,
        duration=spec.duration,
        status=TaskStatus.PENDING,
    )


def compile_reference_graph(
    scene: Scene,
    task_specs: list[tuple[TaskType, str]],
    edges: list[tuple[tuple[TaskType, str], tuple[TaskType, str]]],
) -> TaskGraph:
    """Build an executable TaskGraph from a *trusted* task list.

    ``task_specs`` are (type, target) tuples — priority is scene-derived
    (``derive_priority``, D-022); ``edges`` are (predecessor, successor) pairs
    of (type, target) endpoints. Status is set to PENDING then recomputed to
    the READY frontier.

    Raises ValueError on a broken trusted list — duplicate edge, or an edge
    endpoint that is not one of the compiled tasks — so a bad fixture fails
    loudly instead of silently losing an edge.
    """
    graph = TaskGraph()
    for task_type, target in task_specs:
        priority = derive_priority(scene, task_type, target)
        graph.add_task(compile_task(scene, task_type, target, priority))

    seen: set[tuple[str, str]] = set()
    for (pt, ptgt), (st, stgt) in edges:
        pred, succ = task_id_for(pt, ptgt), task_id_for(st, stgt)
        for endpoint in (pred, succ):
            if endpoint not in graph:
                raise ValueError(f"edge endpoint is not a compiled task: {endpoint}")
        if (pred, succ) in seen:
            raise ValueError(f"duplicate edge: {pred} -> {succ}")
        seen.add((pred, succ))
        graph.add_edge(pred, succ)

    graph.recompute_ready()
    return graph
