"""Deterministic active-team resolution for P13 resource constraints."""

from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import combinations, product

from allocation.allocate import AllocationResult, allocate
from core.enums import PlatformKind
from core.mission_state import MissionState
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

    feasible: list[tuple[tuple[object, ...], MissionState, AllocationResult]] = []
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
        feasible.append((key, candidate, plan))

    if not feasible:
        raise ResourceInfeasibleError(
            "no active team can satisfy the resource request and assign every task"
        )
    _, selected_state, selected_plan = min(feasible, key=lambda item: item[0])
    return TeamAllocation(
        selected_state,
        selected_plan,
        tuple(sorted(selected_state.agents)),
        tested,
    )


__all__ = ["ResourceInfeasibleError", "TeamAllocation", "resolve_initial_team"]
