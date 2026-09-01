"""CBBA scoring: time-discounted reward + marginal score (RESEARCH_CONTRACT.md §11).

Ported from LLM_CBBA research/allocation/scoring.py (see docs/PROVENANCE.md).
The reward/marginal-score shape is the original CBBA paper's (its diminishing-
marginal-gain property depends on the exact form). Adapted here:

- reward(task) = task.priority  (contract §11 formula, not the source's 10*priority)
- travel legs are platform-aware (allocation/travel.py), not a single Euclidean
  formula
- generic Agent instead of UAV

Do not add terms to the reward here — anything new belongs in a P8 module.
"""

from collections.abc import Sequence

from allocation.travel import leg_time, start_ref, task_ref
from core.agent import Agent
from core.task import Task
from scenarios.scene import Scene

# λ, fixed for every experimental condition (contract §11). Reused from LLM_CBBA.
DEFAULT_LAMBDA = 0.999


def reward(task: Task) -> float:
    return float(task.priority)


def path_score(
    agent: Agent,
    path: Sequence[Task],
    scene: Scene,
    lam: float = DEFAULT_LAMBDA,
    start_delay: float = 0.0,
) -> float:
    """S_i(p_i) = Σ_{j in p_i} λ^{completion_time_j} · reward(j).

    completion_time_j is the time the agent finishes j: every travel leg up to
    and including the arrival at j, plus every earlier task's dwell duration.
    ``start_delay`` seeds the clock — for a rolling epoch it is the time until an
    agent that is still executing a task becomes available (0 in P3).
    (§11 writes λ^projected_completion_time; the source discounts at arrival —
    kept consistent here by discounting at completion, i.e. arrival + own dwell.)
    """
    total = 0.0
    ref = start_ref(agent, scene)
    elapsed = start_delay
    for task in path:
        elapsed += leg_time(agent, ref, task, scene)
        elapsed += task.duration
        total += (lam**elapsed) * reward(task)
        ref = task_ref(agent, task, scene)
    return total


def _eligible(agent: Agent, task: Task) -> bool:
    return agent.platform_kind in task.eligible_platforms and agent.has_capabilities(
        task.required_capabilities
    )


def marginal_score(
    agent: Agent,
    task: Task,
    path: Sequence[Task],
    scene: Scene,
    lam: float = DEFAULT_LAMBDA,
    start_delay: float = 0.0,
) -> tuple[float, int]:
    """(c_ij, best insertion index n). -inf/-1 if the agent is not eligible;
    0.0/-1 if the task is already in the path. Every n in [0, len(path)] is tried.
    """
    if any(t.task_id == task.task_id for t in path):
        return 0.0, -1
    if not _eligible(agent, task):
        return float("-inf"), -1

    base = path_score(agent, path, scene, lam, start_delay)
    best_gain, best_n = float("-inf"), -1
    for n in range(len(path) + 1):
        candidate = list(path)
        candidate.insert(n, task)
        gain = path_score(agent, candidate, scene, lam, start_delay) - base
        if gain > best_gain:
            best_gain, best_n = gain, n
    return best_gain, best_n
