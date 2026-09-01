"""Rolling READY-frontier allocation + evaluation metrics (RESEARCH_CONTRACT.md §11, §13).

``allocate`` drives CBBA epoch by epoch over a clone of the mission state: run
``run_epoch`` on the current READY frontier, record the winners, advance a
plan-time simulation (agent positions + task completion times), mark the epoch's
tasks done so the frontier rolls, repeat until every task is placed or the
frontier stalls.

Nothing here is ported — it is the P3 wiring around the ported CBBA core.
"""

from dataclasses import dataclass, replace

from allocation.cbba import DEFAULT_LAMBDA, run_epoch
from allocation.travel import leg_distance, start_ref, task_ref
from core.agent import Agent
from core.enums import PlatformKind, TaskStatus
from core.mission_state import MissionState
from core.task_graph import TaskGraph
from scenarios.scene import Scene


@dataclass
class AllocationResult:
    assignments: dict[str, str]                       # task_id -> agent_id
    winning_bids: dict[str, float]
    task_start: dict[str, float]
    task_completion: dict[str, float]
    consensus_rounds: list[int]                       # one per epoch
    allocation_success: bool
    unassigned_tasks: list[str]
    capability_violations: list[str]
    precedence_violations: list[str]
    uav_flight_distance: float
    ugv_route_distance: float
    estimated_makespan: float
    workload: dict[str, int]                          # agent_id -> task count
    agent_utilization: dict[str, float]               # agent_id -> busy/makespan
    idle_agents: list[str]
    lam: float = DEFAULT_LAMBDA


def _eligible(agent: Agent, task) -> bool:
    return agent.platform_kind in task.eligible_platforms and agent.has_capabilities(
        task.required_capabilities
    )


def _walk(agent, path_ids, graph, scene, start_time, completion):
    """Simulate one agent executing its epoch path; return (end_time, distance,
    per-task start times)."""
    ref = start_ref(agent, scene)
    clock = start_time
    distance = 0.0
    starts: dict[str, float] = {}
    for task_id in path_ids:
        task = graph[task_id]
        d = leg_distance(agent, ref, task, scene)
        clock += d / agent.speed
        pred_ready = max(
            (completion[p] for p in graph.predecessors(task_id) if p in completion),
            default=0.0,
        )
        st = max(clock, pred_ready)
        starts[task_id] = st
        clock = st + task.duration
        completion[task_id] = clock
        distance += d
        ref = task_ref(agent, task, scene)
    return clock, distance, starts


def allocate(
    state: MissionState, scene: Scene, lam: float = DEFAULT_LAMBDA, max_epochs: int = 50
) -> AllocationResult:
    work = state.clone()
    graph = work.graph
    agents = work.agents
    access_nodes = dict(scene.agent_access_nodes)

    assignments: dict[str, str] = {}
    winning_bids: dict[str, float] = {}
    task_start: dict[str, float] = {}
    task_completion: dict[str, float] = {}
    consensus_rounds: list[int] = []
    agent_busy: dict[str, float] = {a: 0.0 for a in agents}
    workload: dict[str, int] = {a: 0 for a in agents}
    uav_flight = 0.0
    ugv_route = 0.0
    agent_free_at: dict[str, float] = {a: 0.0 for a in agents}

    for _ in range(max_epochs):
        graph.recompute_ready()
        frontier = sorted(
            t.task_id
            for t in graph.tasks
            if t.status is TaskStatus.READY and t.task_id not in assignments
        )
        if not frontier:
            break

        for a in agents.values():
            a.bundle, a.path = [], []
        epoch_scene = replace(scene, agent_access_nodes=dict(access_nodes))
        result = run_epoch(
            {t.task_id: t for t in graph.tasks}, agents, epoch_scene, lam=lam, frontier=frontier
        )
        consensus_rounds.append(result.rounds)

        for task_id, agent_id in result.winners.items():
            assignments[task_id] = agent_id
            winning_bids[task_id] = result.winning_bids[task_id]
            workload[agent_id] += 1

        for agent_id, agent in agents.items():
            if not agent.path:
                continue
            end, dist, starts = _walk(
                agent, agent.path, graph, epoch_scene, agent_free_at[agent_id], task_completion
            )
            task_start.update(starts)
            busy = end - agent_free_at[agent_id]
            agent_busy[agent_id] += busy
            agent_free_at[agent_id] = end
            if agent.platform_kind is PlatformKind.UAV:
                uav_flight += dist
                agent.position = task_ref(agent, graph[agent.path[-1]], epoch_scene)
            else:
                ugv_route += dist
                access_nodes[agent_id] = task_ref(agent, graph[agent.path[-1]], epoch_scene)

        for task_id in result.winners:
            graph[task_id].status = TaskStatus.COMPLETED

    unassigned = sorted(t.task_id for t in graph.tasks if t.task_id not in assignments)
    makespan = max(task_completion.values(), default=0.0)

    cap_viol = sorted(
        tid for tid, aid in assignments.items() if not _eligible(agents[aid], graph[tid])
    )
    prec_viol = _precedence_violations(graph, task_start, task_completion)

    utilization = {
        a: (agent_busy[a] / makespan if makespan > 0 else 0.0) for a in agents
    }
    idle = sorted(a for a in agents if workload[a] == 0)

    return AllocationResult(
        assignments=assignments,
        winning_bids=winning_bids,
        task_start=task_start,
        task_completion=task_completion,
        consensus_rounds=consensus_rounds,
        allocation_success=not unassigned,
        unassigned_tasks=unassigned,
        capability_violations=cap_viol,
        precedence_violations=prec_viol,
        uav_flight_distance=uav_flight,
        ugv_route_distance=ugv_route,
        estimated_makespan=makespan,
        workload=workload,
        agent_utilization=utilization,
        idle_agents=idle,
        lam=lam,
    )


def _precedence_violations(
    graph: TaskGraph, task_start: dict[str, float], task_completion: dict[str, float]
) -> list[str]:
    out: list[str] = []
    for pred, succ in sorted(graph.edges):
        if pred in task_completion and succ in task_start:
            if task_completion[pred] > task_start[succ] + 1e-6:
                out.append(f"{pred} -> {succ}")
    return out
