"""2D discrete-event executor for the reference mission (RESEARCH_CONTRACT.md §11, §14).

Runs the real MissionState: assign the READY frontier via CBBA, let each agent
travel (§8) to its committed tasks and dwell for the task duration, complete the
task, recompute the frontier, and — when a completion unlocks a new task — run
another epoch (rolling READY-frontier). Task completion is position-arrival +
dwell only (§3). Agent bundles/paths persist across epochs; already-committed
tasks are carried into the next auction as ``held`` so they are not re-contested.

The premature-deadlock bug (§14): a stale "ready" set used for the deadlock
decision. This loop calls ``recompute_ready`` immediately before deciding that
nothing can progress; the single-agent A->B chain is a P4 gate test.
"""

from dataclasses import dataclass, field, replace

from allocation.cbba import DEFAULT_LAMBDA, run_epoch
from allocation.travel import leg_distance, task_ref
from core.enums import PlatformKind, TaskStatus
from core.mission_state import MissionState
from scenarios.scene import Scene

_EPS = 1e-9
_UNFINISHED = frozenset(
    {TaskStatus.PENDING, TaskStatus.READY, TaskStatus.ASSIGNED, TaskStatus.RUNNING}
)


@dataclass
class ExecutionResult:
    completed: list[str]
    assignments: dict[str, str]
    winning_bids: dict[str, float]
    task_start: dict[str, float]
    task_completion: dict[str, float]
    consensus_rounds: list[int]
    epochs: int
    makespan: float
    capability_violations: list[str]
    precedence_violations: list[str]
    uav_flight_distance: float
    ugv_route_distance: float
    workload: dict[str, int]
    agent_utilization: dict[str, float]
    idle_agents: list[str]
    deadlocked: bool = False
    deadlock_tasks: list[str] = field(default_factory=list)


@dataclass
class _Sim:
    current: str | None = None
    finish_at: float = 0.0
    busy: float = 0.0


def _preds_done(graph, task_id) -> bool:
    return all(graph[p].status is TaskStatus.COMPLETED for p in graph.predecessors(task_id))


class SimExecutor:
    def __init__(self, state: MissionState, scene: Scene, lam: float = DEFAULT_LAMBDA) -> None:
        self.work = state.clone()
        self.graph = self.work.graph
        self.agents = self.work.agents
        self.scene = scene
        self.lam = lam
        self.access_nodes = dict(scene.agent_access_nodes)
        self.sim: dict[str, _Sim] = {aid: _Sim() for aid in self.agents}

        self.now = 0.0
        self.assignments: dict[str, str] = {}
        self.winning_bids: dict[str, float] = {}
        self.task_start: dict[str, float] = {}
        self.task_completion: dict[str, float] = {}
        self.consensus_rounds: list[int] = []
        self.uav_flight = 0.0
        self.ugv_route = 0.0

    def _epoch_scene(self) -> Scene:
        return replace(self.scene, agent_access_nodes=dict(self.access_nodes))

    def _ref(self, agent_id: str):
        agent = self.agents[agent_id]
        if agent.platform_kind is PlatformKind.UAV:
            return agent.position
        return self.access_nodes[agent_id]

    # -- epoch --------------------------------------------------------
    def _run_epoch(self) -> bool:
        frontier = sorted(
            t.task_id
            for t in self.graph.tasks
            if t.status is TaskStatus.READY and t.task_id not in self.assignments
        )
        if not frontier:
            return False

        held = {
            tid: (aid, self.winning_bids[tid])
            for tid, aid in self.assignments.items()
            if self.graph[tid].status is not TaskStatus.COMPLETED
        }
        tasks_dict = {
            t.task_id: t for t in self.graph.tasks if t.status is not TaskStatus.COMPLETED
        }
        epoch_scene = self._epoch_scene()

        # Bid from where each agent will be once its running task finishes.
        projected: dict[str, tuple] = {}
        for aid, agent in self.agents.items():
            running = self.sim[aid].current
            if running is None:
                continue
            projected[aid] = (agent.position, self.access_nodes.get(aid))
            landing = task_ref(agent, self.graph[running], epoch_scene)
            if agent.platform_kind is PlatformKind.UAV:
                agent.position = landing
            else:
                self.access_nodes[aid] = landing

        result = run_epoch(
            tasks_dict, self.agents, self._epoch_scene(), lam=self.lam,
            frontier=frontier, held=held,
        )

        for aid, (pos, node) in projected.items():
            self.agents[aid].position = pos
            if node is not None:
                self.access_nodes[aid] = node

        self.consensus_rounds.append(result.rounds)
        if not result.winners:
            return False
        for tid, aid in result.winners.items():
            self.assignments[tid] = aid
            self.winning_bids[tid] = result.winning_bids[tid]
            self.graph[tid].status = TaskStatus.ASSIGNED
            self.graph[tid].assigned_agent = aid

        # A running task must stay at the head of its agent's path.
        for aid, agent in self.agents.items():
            running = self.sim[aid].current
            if running is not None and agent.path and agent.path[0] != running:
                agent.path.remove(running)
                agent.path.insert(0, running)
        return True

    # -- dispatch / advance ----------------------------------------
    def _dispatch(self) -> bool:
        moved = False
        for agent_id in sorted(self.agents):
            s = self.sim[agent_id]
            agent = self.agents[agent_id]
            if s.current is not None or not agent.path:
                continue
            task_id = agent.path[0]
            if not _preds_done(self.graph, task_id):
                continue
            task = self.graph[task_id]
            dist = leg_distance(agent, self._ref(agent_id), task, self._epoch_scene())
            travel = dist / agent.speed
            s.current = task_id
            self.task_start[task_id] = self.now + travel
            s.finish_at = self.now + travel + task.duration
            s.busy += travel + task.duration
            task.status = TaskStatus.RUNNING
            if agent.platform_kind is PlatformKind.UAV:
                self.uav_flight += dist
            else:
                self.ugv_route += dist
            moved = True
        return moved

    def _advance(self) -> None:
        working = [aid for aid, s in self.sim.items() if s.current is not None]
        self.now = min(self.sim[aid].finish_at for aid in working)
        for agent_id in sorted(working):
            s = self.sim[agent_id]
            if s.finish_at > self.now + _EPS:
                continue
            task_id = s.current
            task = self.graph[task_id]
            agent = self.agents[agent_id]
            task.status = TaskStatus.COMPLETED
            self.task_completion[task_id] = self.now
            landing = task_ref(agent, task, self._epoch_scene())
            if agent.platform_kind is PlatformKind.UAV:
                agent.position = landing
            else:
                self.access_nodes[agent_id] = landing
            if task_id in agent.path:
                agent.path.remove(task_id)
            if task_id in agent.bundle:
                agent.bundle.remove(task_id)
            s.current = None

    # -- run --------------------------------------------------------
    def run(self, max_steps: int = 10_000) -> ExecutionResult:
        self.graph.recompute_ready()
        self._run_epoch()

        for _ in range(max_steps):
            if all(t.status not in _UNFINISHED for t in self.graph.tasks):
                break
            if self._dispatch():
                continue
            if any(s.current is not None for s in self.sim.values()):
                self._advance()
                self.graph.recompute_ready()  # a completion may unlock a task
                self._run_epoch()
                continue
            # Nobody is working, nothing dispatched. Recompute the frontier ONE
            # more time before declaring deadlock (§14), then try an epoch.
            self.graph.recompute_ready()
            if self._run_epoch():
                continue
            break

        return self._result()

    def _result(self) -> ExecutionResult:
        unfinished = sorted(t.task_id for t in self.graph.tasks if t.status in _UNFINISHED)
        completed = sorted(
            t.task_id for t in self.graph.tasks if t.status is TaskStatus.COMPLETED
        )
        makespan = max(self.task_completion.values(), default=0.0)
        kind = {aid: a.platform_kind for aid, a in self.agents.items()}

        cap_viol = sorted(
            tid
            for tid, aid in self.assignments.items()
            if not (
                kind[aid] in self.graph[tid].eligible_platforms
                and self.agents[aid].has_capabilities(self.graph[tid].required_capabilities)
            )
        )
        prec_viol = [
            f"{p} -> {s}"
            for p, s in sorted(self.graph.edges)
            if p in self.task_completion
            and s in self.task_start
            and self.task_completion[p] > self.task_start[s] + 1e-6
        ]
        workload: dict[str, int] = {aid: 0 for aid in self.agents}
        for aid in self.assignments.values():
            workload[aid] += 1

        return ExecutionResult(
            completed=completed,
            assignments=self.assignments,
            winning_bids=self.winning_bids,
            task_start=self.task_start,
            task_completion=self.task_completion,
            consensus_rounds=self.consensus_rounds,
            epochs=len(self.consensus_rounds),
            makespan=makespan,
            capability_violations=cap_viol,
            precedence_violations=prec_viol,
            uav_flight_distance=self.uav_flight,
            ugv_route_distance=self.ugv_route,
            workload=workload,
            agent_utilization={
                aid: (self.sim[aid].busy / makespan if makespan > 0 else 0.0)
                for aid in self.agents
            },
            idle_agents=sorted(aid for aid, n in workload.items() if n == 0),
            deadlocked=bool(unfinished),
            deadlock_tasks=unfinished,
        )
