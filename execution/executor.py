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
from enum import Enum

from allocation.cbba import DEFAULT_LAMBDA, run_epoch
from allocation.travel import leg_distance, task_ref
from core.enums import PlatformKind, TaskStatus
from core.mission_state import MissionState
from scenarios.scene import Scene

_EPS = 1e-9
_UNFINISHED = frozenset(
    {TaskStatus.PENDING, TaskStatus.READY, TaskStatus.ASSIGNED, TaskStatus.RUNNING}
)


class Termination(str, Enum):
    COMPLETED = "COMPLETED"
    DEADLOCK = "DEADLOCK"
    STEP_LIMIT = "STEP_LIMIT"


@dataclass
class ExecutionResult:
    termination: Termination
    completed: list[str]
    assignments: dict[str, str]
    winning_bids: dict[str, float]
    task_departure: dict[str, float]
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
    unfinished_tasks: list[str] = field(default_factory=list)

    @property
    def deadlocked(self) -> bool:
        return self.termination is Termination.DEADLOCK


@dataclass
class _Sim:
    current: str | None = None
    finish_at: float = 0.0
    busy: float = 0.0


@dataclass(frozen=True, slots=True)
class _SimSnapshot:
    current: str | None
    finish_at: float
    busy: float


@dataclass(frozen=True, slots=True)
class ExecutionCheckpoint:
    """Deep executor snapshot at a deterministic event boundary (§19.2).

    ``_work`` is intentionally private and is cloned both when the checkpoint
    is created and when it is restored.  The public API never hands its mutable
    graph/agents to a caller, so advancing either executor cannot mutate a
    previously captured checkpoint.
    """

    _work: MissionState = field(repr=False)
    now: float
    access_nodes: tuple[tuple[str, str], ...]
    sim: tuple[tuple[str, _SimSnapshot], ...]
    assignments: tuple[tuple[str, str], ...]
    winning_bids: tuple[tuple[str, float], ...]
    task_departure: tuple[tuple[str, float], ...]
    task_start: tuple[tuple[str, float], ...]
    task_completion: tuple[tuple[str, float], ...]
    consensus_rounds: tuple[int, ...]
    uav_flight: float
    ugv_route: float
    lam: float
    started: bool
    epoch_pending: bool


@dataclass(frozen=True, slots=True)
class CompletionAdvance:
    """Result of advancing to one completion event or a terminal state."""

    checkpoint: ExecutionCheckpoint
    completed_now: tuple[str, ...]
    execution: ExecutionResult | None = None


def _preds_done(graph, task_id) -> bool:
    return all(graph[p].status is TaskStatus.COMPLETED for p in graph.predecessors(task_id))


class SimExecutor:
    def __init__(self, state: MissionState, scene: Scene, lam: float = DEFAULT_LAMBDA) -> None:
        self.work = state.clone()
        self.graph = self.work.graph
        self.agents = self.work.agents
        self.scene = scene
        self.lam = lam
        self.access_nodes = {
            aid: node for aid, node in scene.agent_access_nodes.items() if aid in self.agents
        }
        self.sim: dict[str, _Sim] = {aid: _Sim() for aid in self.agents}

        for agent in self.agents.values():
            agent.current_task = None

        self.now = 0.0
        self.assignments: dict[str, str] = {}
        self.winning_bids: dict[str, float] = {}
        self.task_departure: dict[str, float] = {}
        self.task_start: dict[str, float] = {}
        self.task_completion: dict[str, float] = {}
        self.consensus_rounds: list[int] = []
        self.uav_flight = 0.0
        self.ugv_route = 0.0
        self._started = False
        self._epoch_pending = False

    # -- checkpoint / restore (§19.2) --------------------------------
    def checkpoint(self) -> ExecutionCheckpoint:
        return ExecutionCheckpoint(
            _work=self.work.clone(),
            now=self.now,
            access_nodes=tuple(sorted(self.access_nodes.items())),
            sim=tuple(
                (aid, _SimSnapshot(value.current, value.finish_at, value.busy))
                for aid, value in sorted(self.sim.items())
            ),
            assignments=tuple(sorted(self.assignments.items())),
            winning_bids=tuple(sorted(self.winning_bids.items())),
            task_departure=tuple(sorted(self.task_departure.items())),
            task_start=tuple(sorted(self.task_start.items())),
            task_completion=tuple(sorted(self.task_completion.items())),
            consensus_rounds=tuple(self.consensus_rounds),
            uav_flight=self.uav_flight,
            ugv_route=self.ugv_route,
            lam=self.lam,
            started=self._started,
            epoch_pending=self._epoch_pending,
        )

    @classmethod
    def from_checkpoint(
        cls,
        checkpoint: ExecutionCheckpoint,
        scene: Scene,
    ) -> "SimExecutor":
        if not isinstance(checkpoint, ExecutionCheckpoint):
            raise TypeError("checkpoint must be an ExecutionCheckpoint")
        executor = cls.__new__(cls)
        executor.work = checkpoint._work.clone()
        executor.graph = executor.work.graph
        executor.agents = executor.work.agents
        executor.scene = scene
        executor.lam = checkpoint.lam
        executor.access_nodes = dict(checkpoint.access_nodes)
        executor.sim = {
            aid: _Sim(value.current, value.finish_at, value.busy)
            for aid, value in checkpoint.sim
        }
        if set(executor.sim) != set(executor.agents):
            raise ValueError("checkpoint sim agents do not match MissionState agents")
        if set(executor.access_nodes) - set(executor.agents):
            raise ValueError("checkpoint access nodes reference unknown agents")
        executor.now = checkpoint.now
        executor.assignments = dict(checkpoint.assignments)
        executor.winning_bids = dict(checkpoint.winning_bids)
        executor.task_departure = dict(checkpoint.task_departure)
        executor.task_start = dict(checkpoint.task_start)
        executor.task_completion = dict(checkpoint.task_completion)
        executor.consensus_rounds = list(checkpoint.consensus_rounds)
        executor.uav_flight = checkpoint.uav_flight
        executor.ugv_route = checkpoint.ugv_route
        executor._started = checkpoint.started
        executor._epoch_pending = checkpoint.epoch_pending
        return executor

    def _prepare_epoch(self) -> None:
        if not self._started:
            self.graph.recompute_ready()
            self._run_epoch()
            self._started = True
            self._epoch_pending = False
        elif self._epoch_pending:
            self._run_epoch()
            self._epoch_pending = False

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

        # Residual-path view for bidding (D-012/D-013): a RUNNING task is removed
        # from its agent's path, the agent bids from where it will land, and
        # start_delay = its remaining execution time — so its travel/dwell/reward
        # is not double-counted AND its unavailability still costs it.
        saved_ref: dict[str, tuple] = {}
        start_delays: dict[str, float] = {}
        for aid, agent in self.agents.items():
            running = self.sim[aid].current
            if running is None:
                continue
            if running in agent.path:
                agent.path.remove(running)
            start_delays[aid] = max(0.0, self.sim[aid].finish_at - self.now)
            saved_ref[aid] = (agent.position, self.access_nodes.get(aid))
            landing = task_ref(agent, self.graph[running], epoch_scene)
            if agent.platform_kind is PlatformKind.UAV:
                agent.position = landing
            else:
                self.access_nodes[aid] = landing

        result = run_epoch(
            tasks_dict, self.agents, self._epoch_scene(), lam=self.lam,
            frontier=frontier, held=held, start_delays=start_delays,
        )

        for aid, (pos, node) in saved_ref.items():
            self.agents[aid].position = pos
            if node is not None:
                self.access_nodes[aid] = node
        for aid in saved_ref:  # re-merge the RUNNING task at the path head
            self.agents[aid].path.insert(0, self.sim[aid].current)

        self.consensus_rounds.append(result.rounds)
        if not result.winners:
            return False
        for tid, aid in result.winners.items():
            self.assignments[tid] = aid
            self.winning_bids[tid] = result.winning_bids[tid]
            self.graph[tid].status = TaskStatus.ASSIGNED
            self.graph[tid].assigned_agent = aid
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
            agent.current_task = task_id
            self.task_departure[task_id] = self.now
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

    def _advance(self) -> tuple[str, ...]:
        working = [aid for aid, s in self.sim.items() if s.current is not None]
        self.now = min(self.sim[aid].finish_at for aid in working)
        completed_now: list[str] = []
        for agent_id in sorted(working):
            s = self.sim[agent_id]
            if s.finish_at > self.now + _EPS:
                continue
            task_id = s.current
            task = self.graph[task_id]
            agent = self.agents[agent_id]
            task.status = TaskStatus.COMPLETED
            task.assigned_agent = None  # §10 invariant: COMPLETED carries no assignment
            agent.current_task = None
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
            completed_now.append(task_id)
        return tuple(sorted(completed_now))

    def advance_to_next_completion(self, max_steps: int = 10_000) -> CompletionAdvance:
        """Advance to exactly one task-completion event, then pause (§19.2).

        READY is recomputed after the event, but its auction is deferred until
        resume.  This is the deterministic window in which an online command
        may add another READY task before the next CBBA epoch.
        """
        self._prepare_epoch()
        for _ in range(max_steps):
            if all(t.status not in _UNFINISHED for t in self.graph.tasks):
                result = self._result(Termination.COMPLETED)
                return CompletionAdvance(self.checkpoint(), (), result)
            if self._dispatch():
                continue
            if any(s.current is not None for s in self.sim.values()):
                completed = self._advance()
                self.graph.recompute_ready()
                self._epoch_pending = True
                result = None
                if all(t.status not in _UNFINISHED for t in self.graph.tasks):
                    result = self._result(Termination.COMPLETED)
                return CompletionAdvance(self.checkpoint(), completed, result)
            self.graph.recompute_ready()
            if self._run_epoch():
                self._started = True
                self._epoch_pending = False
                continue
            result = self._result(Termination.DEADLOCK)
            return CompletionAdvance(self.checkpoint(), (), result)

        result = self._result(Termination.STEP_LIMIT)
        return CompletionAdvance(self.checkpoint(), (), result)

    # -- run --------------------------------------------------------
    def run(self, max_steps: int = 10_000) -> ExecutionResult:
        self._prepare_epoch()

        termination = Termination.STEP_LIMIT
        for _ in range(max_steps):
            if all(t.status not in _UNFINISHED for t in self.graph.tasks):
                termination = Termination.COMPLETED
                break
            if self._dispatch():
                continue
            if any(s.current is not None for s in self.sim.values()):
                self._advance()
                self.graph.recompute_ready()  # a completion may unlock a task
                self._run_epoch()
                self._epoch_pending = False
                continue
            # Nobody is working, nothing dispatched. Recompute the frontier ONE
            # more time before declaring deadlock (§14), then try an epoch.
            self.graph.recompute_ready()
            if self._run_epoch():
                continue
            termination = Termination.DEADLOCK
            break

        # A completion on the final allowed step still counts as COMPLETED
        # (the loop check runs at the top of an iteration that never comes).
        if all(t.status not in _UNFINISHED for t in self.graph.tasks):
            termination = Termination.COMPLETED
        return self._result(termination)

    def _result(self, termination: Termination) -> ExecutionResult:
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
        # §13: an agent must not depart toward a task before its predecessors
        # complete (contract "no travel before READY"), so compare against
        # departure, not arrival.
        prec_viol = [
            f"{p} -> {s}"
            for p, s in sorted(self.graph.edges)
            if p in self.task_completion
            and s in self.task_departure
            and self.task_completion[p] > self.task_departure[s] + 1e-6
        ]
        workload: dict[str, int] = {aid: 0 for aid in self.agents}
        for aid in self.assignments.values():
            workload[aid] += 1

        # busy is booked at dispatch, so a STEP_LIMIT run with in-flight tasks
        # would report utilization > 1 — not a usable figure (§14, D-014).
        if termination is Termination.STEP_LIMIT:
            utilization: dict[str, float] = {}
        else:
            utilization = {
                aid: (self.sim[aid].busy / makespan if makespan > 0 else 0.0)
                for aid in self.agents
            }

        return ExecutionResult(
            termination=termination,
            completed=completed,
            assignments=self.assignments,
            winning_bids=self.winning_bids,
            task_departure=self.task_departure,
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
            agent_utilization=utilization,
            idle_agents=sorted(aid for aid, n in workload.items() if n == 0),
            unfinished_tasks=unfinished,
        )


__all__ = [
    "CompletionAdvance",
    "ExecutionCheckpoint",
    "ExecutionResult",
    "SimExecutor",
    "Termination",
]
