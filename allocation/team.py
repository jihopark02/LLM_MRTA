"""Deterministic active-team resolution for P13 resource constraints."""

from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import combinations, product

from allocation.allocate import AllocationResult, allocate
from core.enums import PlatformKind, TaskStatus
from core.mission_state import MissionState
from execution.executor import SimExecutor, Termination
from interaction.resources import ResourceRequest
from scenarios.scene import Scene


class ResourceInfeasibleError(ValueError):
    """No active fleet subset can satisfy both the request and the mission."""

    code = "RESOURCE_INFEASIBLE"


@dataclass(frozen=True, slots=True)
class TeamAllocation:
    state: MissionState
    plan: AllocationResult
    active_agents: tuple[str, ...]
    candidates_tested: int


@dataclass(frozen=True, slots=True)
class RuntimeTeamAllocation:
    executor: SimExecutor
    active_agents: tuple[str, ...]
    candidates_tested: int
    released_tasks: tuple[str, ...]
    deferred_exclusions: tuple[str, ...]
    consensus_rounds: tuple[int, ...]


def _copy_for_team(state: MissionState, agent_ids: tuple[str, ...]) -> MissionState:
    return MissionState(
        graph=state.graph.clone(),
        agents={
            agent_id: replace(
                state.agents[agent_id],
                bundle=list(state.agents[agent_id].bundle),
                path=list(state.agents[agent_id].path),
            )
            for agent_id in agent_ids
        },
        winning_bids={
            task_id: bid
            for task_id, bid in state.winning_bids.items()
            if state.graph[task_id].assigned_agent in agent_ids
        },
    )


def _platform_teams(
    state: MissionState,
    request: ResourceRequest,
    platform: PlatformKind,
) -> tuple[tuple[str, ...], ...]:
    excluded = set(request.excluded_agents)
    available = tuple(
        sorted(
            agent_id
            for agent_id, agent in state.agents.items()
            if agent.platform_kind is platform and agent_id not in excluded
        )
    )
    required = tuple(
        sorted(agent_id for agent_id in request.required_agents if agent_id in available)
    )
    required_set = set(required)
    constraint = request.count_for(platform)

    # An unconstrained platform retains every non-excluded agent, preserving
    # the baseline path exactly instead of turning team minimisation on by accident.
    if not constraint.constrained:
        return (available,)

    teams: list[tuple[str, ...]] = []
    optional = tuple(agent_id for agent_id in available if agent_id not in required_set)
    for size in constraint.permitted_sizes(len(available)):
        if size < len(required):
            continue
        for chosen in combinations(optional, size - len(required)):
            teams.append(tuple(sorted((*required, *chosen))))
    return tuple(teams)


def resolve_initial_team(
    state: MissionState,
    scene: Scene,
    request: ResourceRequest,
    *,
    planner=allocate,
) -> TeamAllocation:
    """Choose a feasible team without changing CBBA or its scoring.

    P13.1 is intentionally initial-mission only.  Callers provide a fresh
    unexecuted state; online policy replacement belongs to P13.2.
    """
    request.validate_scene(scene)
    if set(state.agents) != {agent.agent_id for agent in scene.fleet}:
        raise ValueError("initial team resolution requires the complete scene fleet")

    if not request.constrained:
        plan = planner(state, scene)
        return TeamAllocation(state, plan, tuple(sorted(state.agents)), 1)

    required = set(request.required_agents)
    options = (
        _platform_teams(state, request, PlatformKind.UAV),
        _platform_teams(state, request, PlatformKind.UGV),
    )
    if not options[0] or not options[1]:
        raise ResourceInfeasibleError("resource counts admit no active team")

    feasible: list[tuple[tuple[object, ...], tuple[str, ...], AllocationResult]] = []
    tested = 0
    for uav_ids, ugv_ids in product(*options):
        agent_ids = tuple(sorted((*uav_ids, *ugv_ids)))
        candidate = _copy_for_team(state, agent_ids)
        tested += 1
        if not agent_ids and len(candidate.graph) > 0:
            continue
        plan = planner(candidate, scene)
        assigned_agents = set(plan.assignments.values())
        if (
            not plan.allocation_success
            or plan.capability_violations
            or plan.precedence_violations
            or not required <= assigned_agents
        ):
            continue
        key: tuple[object, ...] = (
            plan.estimated_makespan,
            plan.uav_flight_distance + plan.ugv_route_distance,
            len(agent_ids),
            agent_ids,
        )
        feasible.append((key, agent_ids, plan))

    if not feasible:
        raise ResourceInfeasibleError(
            "no active team can satisfy the resource request and assign every task"
        )
    _, selected_agents, selected_plan = min(feasible, key=lambda item: item[0])
    return TeamAllocation(
        state,
        selected_plan,
        selected_agents,
        tested,
    )


def resolve_runtime_team(
    executor: SimExecutor,
    scene: Scene,
    request: ResourceRequest,
) -> RuntimeTeamAllocation:
    """Resolve and prepare an active-team replacement on a checkpoint clone.

    Candidate futures are rolled out only to prove residual feasibility and
    rank them.  The returned executor remains at the current checkpoint; none
    of the speculative future clock/task status is published (D-057).
    """
    request.validate_scene(scene)
    if set(executor.agents) != {agent.agent_id for agent in scene.fleet}:
        raise ValueError("runtime team resolution requires the complete scene fleet roster")

    options = (
        _platform_teams(executor.work, request, PlatformKind.UAV),
        _platform_teams(executor.work, request, PlatformKind.UGV),
    )
    if not options[0] or not options[1]:
        raise ResourceInfeasibleError("resource counts admit no active team")

    completed_before = {
        task.task_id
        for task in executor.graph.tasks
        if task.status is TaskStatus.COMPLETED
    }
    required = set(request.required_agents)
    feasible: list[
        tuple[
            tuple[object, ...],
            SimExecutor,
            tuple[str, ...],
            tuple[str, ...],
            tuple[int, ...],
        ]
    ] = []
    tested = 0
    for uav_ids, ugv_ids in product(*options):
        agent_ids = tuple(sorted((*uav_ids, *ugv_ids)))
        candidate = SimExecutor.from_checkpoint(executor.checkpoint(), scene)
        tested += 1
        released, deferred, rounds = candidate.replace_active_team(
            agent_ids,
            rebid_agent_ids=request.required_agents,
        )
        future = SimExecutor.from_checkpoint(candidate.checkpoint(), scene).run()
        residual_assignments = {
            task_id: agent_id
            for task_id, agent_id in future.assignments.items()
            if task_id not in completed_before
        }
        if (
            future.termination is not Termination.COMPLETED
            or future.capability_violations
            or future.precedence_violations
            or not required <= set(residual_assignments.values())
        ):
            continue
        key: tuple[object, ...] = (
            future.makespan - executor.now,
            (future.uav_flight_distance - executor.uav_flight)
            + (future.ugv_route_distance - executor.ugv_route),
            len(agent_ids),
            agent_ids,
        )
        feasible.append((key, candidate, released, deferred, rounds))

    if not feasible:
        raise ResourceInfeasibleError(
            "no active team can satisfy the resource request and complete residual work"
        )
    key, selected, released, deferred, rounds = min(
        feasible, key=lambda item: item[0]
    )
    del key
    return RuntimeTeamAllocation(
        executor=selected,
        active_agents=selected.active_agent_ids,
        candidates_tested=tested,
        released_tasks=released,
        deferred_exclusions=deferred,
        consensus_rounds=rounds,
    )


__all__ = [
    "ResourceInfeasibleError",
    "RuntimeTeamAllocation",
    "TeamAllocation",
    "resolve_initial_team",
    "resolve_runtime_team",
]
