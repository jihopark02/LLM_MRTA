"""CBBA: bundle construction (Phase 1) + consensus (Phase 2) — RESEARCH_CONTRACT.md §11.

Ported from LLM_CBBA research/allocation/cbba.py (see docs/PROVENANCE.md). Standard
CBBA (Choi, Brunet & How, 2009); the ``_action_rule`` table is the paper's Table I
transcribed branch for branch. No new theory here (contract §0, §11).

Adapted: generic ``Agent`` instead of UAV; scoring is platform-aware
(allocation/scoring.py); READY-only auction pool comes from the caller. One
``run_epoch`` call is one scheduling epoch over the current READY frontier
(contract §11 rolling READY-frontier).

Agents' ``bundle``/``path`` are mutated in place for the auction — the caller
resets them per epoch.
"""

from dataclasses import dataclass, field

from allocation.scoring import DEFAULT_LAMBDA, marginal_score
from core.agent import Agent
from core.enums import TaskStatus
from core.task import Task
from scenarios.scene import Scene

EPSILON = 1e-9


class ConvergenceError(RuntimeError):
    pass


def _bid_gt(a: float, b: float) -> bool:
    """Strict > with a float tie tolerance: a near-tie is never '>'."""
    return a > b + EPSILON


def _beats(y_k: float, k: str, y_i: float, i: str) -> bool:
    """Does agent k's bid beat agent i's? Strict > beyond EPSILON; bids within
    EPSILON (1e-9) are a tie, broken by the lexicographically smaller agent_id
    (contract §11 / D-010 deterministic tie-break)."""
    if _bid_gt(y_k, y_i):
        return True
    if _bid_gt(y_i, y_k):
        return False
    return k < i


@dataclass
class CBBAState:
    y: dict[str, dict[str, float]]           # winning bids, per agent's view
    z: dict[str, dict[str, str | None]]      # winning agents
    s: dict[str, dict[str, float]]           # timestamp vector (CBBA eq. 5)

    @classmethod
    def initialize(
        cls,
        agent_ids: list[str],
        task_ids: list[str],
        held: dict[str, tuple[str, float]] | None = None,
    ) -> "CBBAState":
        """``held`` maps an already-committed task to (winner, bid) — every agent
        starts believing that, so it is never re-contested (rolling epochs)."""
        held = held or {}
        y = {i: dict.fromkeys(task_ids, 0.0) for i in agent_ids}
        z: dict[str, dict[str, str | None]] = {i: dict.fromkeys(task_ids) for i in agent_ids}
        for task_id, (winner, bid) in held.items():
            for i in agent_ids:
                y[i][task_id] = bid
                z[i][task_id] = winner
        return cls(y=y, z=z, s={i: dict.fromkeys(agent_ids, 0.0) for i in agent_ids})


@dataclass
class EpochResult:
    rounds: int
    winners: dict[str, str]           # task_id -> agent_id (converged)
    winning_bids: dict[str, float]    # task_id -> bid
    unassigned_frontier_rounds: int = 0
    state: CBBAState | None = field(default=None, repr=False)


def _bundle_build(
    agent: Agent,
    tasks: dict[str, Task],
    frontier: list[str],
    state: CBBAState,
    scene: Scene,
    lam: float,
    capacity: int,
) -> None:
    while len(agent.bundle) < capacity:
        best_id: str | None = None
        best_gain = float("-inf")
        best_n = -1
        for task_id in sorted(frontier):  # deterministic order
            if task_id in agent.bundle:
                continue
            path = [tasks[t] for t in agent.path]
            gain, n = marginal_score(agent, tasks[task_id], path, scene, lam)
            if not _bid_gt(gain, state.y[agent.agent_id][task_id]):
                continue
            if _bid_gt(gain, best_gain):
                best_gain, best_id, best_n = gain, task_id, n
        if best_id is None:
            return
        agent.bundle.append(best_id)
        agent.path.insert(best_n, best_id)
        state.y[agent.agent_id][best_id] = best_gain
        state.z[agent.agent_id][best_id] = agent.agent_id


def _action_rule(z_ij, y_ij, s_i, z_kj, y_kj, s_k, i, k) -> str:
    """"update" | "reset" | "leave" — CBBA paper Table I (rows: sender k's z_kj,
    cols: receiver i's z_ij). Transcribed branch for branch from the source."""

    def sk(a: str) -> float:
        return s_k.get(a, 0.0)

    def si(a: str) -> float:
        return s_i.get(a, 0.0)

    if z_kj == k:
        if z_ij == i:
            return "update" if _beats(y_kj, k, y_ij, i) else "leave"
        if z_ij == k:
            return "update"
        if z_ij is None:
            return "update"
        m = z_ij
        return "update" if (_bid_gt(sk(m), si(m)) or _beats(y_kj, k, y_ij, i)) else "leave"

    if z_kj == i:
        if z_ij == i:
            return "leave"
        if z_ij == k:
            return "reset"
        if z_ij is None:
            return "leave"
        m = z_ij
        return "reset" if _bid_gt(sk(m), si(m)) else "leave"

    if z_kj is None:
        if z_ij == i:
            return "leave"
        if z_ij == k:
            return "update"
        if z_ij is None:
            return "leave"
        m = z_ij
        return "update" if _bid_gt(sk(m), si(m)) else "leave"

    m = z_kj  # m not in {i, k}
    if z_ij == i:
        return "update" if (_bid_gt(sk(m), si(m)) and _beats(y_kj, k, y_ij, i)) else "leave"
    if z_ij == k:
        return "update" if _bid_gt(sk(m), si(m)) else "reset"
    if z_ij == m:
        return "update" if _bid_gt(sk(m), si(m)) else "leave"
    if z_ij is None:
        return "update" if _bid_gt(sk(m), si(m)) else "leave"
    n = z_ij  # n not in {i, k, m}
    if _bid_gt(sk(m), si(m)) and _bid_gt(sk(n), si(n)):
        return "update"
    if _bid_gt(sk(m), si(m)) and _beats(y_kj, k, y_ij, i):
        return "update"
    if _bid_gt(sk(n), si(n)) and _bid_gt(si(m), sk(m)):
        return "reset"
    return "leave"


def _consensus_round(
    agents: dict[str, Agent], task_ids: list[str], state: CBBAState, rnd: int
) -> None:
    """One synchronous fully-connected Phase 2 round against a start-of-round snapshot."""
    ids = sorted(agents)
    snap_y = {i: dict(state.y[i]) for i in ids}
    snap_z = {i: dict(state.z[i]) for i in ids}
    snap_s = {i: dict(state.s[i]) for i in ids}

    for i in ids:
        for k in ids:
            if k == i:
                continue
            for j in task_ids:
                action = _action_rule(
                    state.z[i][j], state.y[i][j], state.s[i],
                    snap_z[k][j], snap_y[k][j], snap_s[k], i, k,
                )
                if action == "update":
                    state.y[i][j] = snap_y[k][j]
                    state.z[i][j] = snap_z[k][j]
                elif action == "reset":
                    state.y[i][j] = 0.0
                    state.z[i][j] = None
            state.s[i][k] = float(rnd)
            for m in ids:
                if m != i:
                    state.s[i][m] = max(state.s[i][m], snap_s[k][m])


def _release_suffix(agent: Agent, state: CBBAState) -> None:
    """If the earliest bundle task this agent no longer wins is at index n̄, drop it
    and every task bid after it; only tasks strictly after n̄ have (y, z) reset."""
    n_bar = None
    for n, task_id in enumerate(agent.bundle):
        if state.z[agent.agent_id][task_id] != agent.agent_id:
            n_bar = n
            break
    if n_bar is None:
        return
    to_remove = set(agent.bundle[n_bar:])
    for task_id in agent.bundle[n_bar + 1:]:
        state.y[agent.agent_id][task_id] = 0.0
        state.z[agent.agent_id][task_id] = None
    agent.bundle = agent.bundle[:n_bar]
    agent.path = [t for t in agent.path if t not in to_remove]


def _snapshot(agents, state) -> tuple:
    return (
        {i: dict(state.y[i]) for i in state.y},
        {i: dict(state.z[i]) for i in state.z},
        {a: (tuple(ag.bundle), tuple(ag.path)) for a, ag in agents.items()},
    )


def run_epoch(
    tasks: dict[str, Task],
    agents: dict[str, Agent],
    scene: Scene,
    lam: float = DEFAULT_LAMBDA,
    capacity: int | None = None,
    frontier: list[str] | None = None,
    held: dict[str, tuple[str, float]] | None = None,
    network_diameter: int = 1,
) -> EpochResult:
    """Run CBBA to convergence over the current READY frontier. Mutates
    agent.bundle/agent.path in place. ``held`` locks already-committed tasks
    (see CBBAState.initialize) so rolling epochs do not re-contest them.
    """
    if frontier is None:
        frontier = sorted(t.task_id for t in tasks.values() if t.status is TaskStatus.READY)
    frontier = sorted(frontier)
    if capacity is None:
        capacity = len(frontier) + max(len(a.bundle) for a in agents.values())

    all_ids = sorted(tasks)
    agent_ids = sorted(agents)
    state = CBBAState.initialize(agent_ids, all_ids, held)

    max_rounds = 10 * max(len(all_ids), 1)
    unchanged = 0
    rnd = 0
    unassigned_rounds = 0

    while unchanged < network_diameter + 1:
        rnd += 1
        if rnd > max_rounds:
            raise ConvergenceError(f"CBBA did not converge within {max_rounds} rounds")
        before = _snapshot(agents, state)
        for aid in agent_ids:
            _bundle_build(agents[aid], tasks, frontier, state, scene, lam, capacity)
        _consensus_round(agents, all_ids, state, rnd)
        unassigned_rounds += sum(
            1 for j in frontier if not any(state.z[i][j] == i for i in agent_ids)
        )
        for aid in agent_ids:
            _release_suffix(agents[aid], state)
        unchanged = unchanged + 1 if before == _snapshot(agents, state) else 0

    ref = agent_ids[0]
    winners = {j: state.z[ref][j] for j in frontier if state.z[ref][j] is not None}
    winning_bids = {j: state.y[ref][j] for j in winners}
    return EpochResult(rnd, winners, winning_bids, unassigned_rounds, state)
