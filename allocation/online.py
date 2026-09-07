"""P9 bidder-connected selective release (contract §19.3).

Release the unstarted assignments whose eligible bidders overlap the new READY
tasks', then rebid them together.  Step 3 also carries any assignment queued
*behind* an affected one in the same bundle — a conservative rule that protects
bundle prefix commitments, **not a demonstrated result**: on every reachable
online path a canonical update makes only THERMAL_RECON READY, whose bidders are
every UAV, so no agent can hold a mixed affected/unaffected bundle and
``released == directly_affected`` always (§19.3, D-041).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from core.enums import TaskStatus
from execution.executor import SimExecutor
from scenarios.scene import Scene
from validator.patch import MissionPatch
from validator.patch_apply import PatchResult, apply_patch

ONLINE_POLICY_VERSION = "1.0"


class ReleasePolicy(str, Enum):
    NO_RESET = "no-reset"
    FULL_RESET = "full-reset"
    SELECTIVE = "selective"


@dataclass(frozen=True, slots=True)
class AssignmentChanges:
    added: dict[str, str] = field(default_factory=dict)
    removed: dict[str, str] = field(default_factory=dict)
    changed: dict[str, tuple[str, str]] = field(default_factory=dict)

    @staticmethod
    def between(before: dict[str, str], after: dict[str, str]) -> AssignmentChanges:
        return AssignmentChanges(
            added={task: after[task] for task in sorted(after.keys() - before.keys())},
            removed={task: before[task] for task in sorted(before.keys() - after.keys())},
            changed={
                task: (before[task], after[task])
                for task in sorted(before.keys() & after.keys())
                if before[task] != after[task]
            },
        )


@dataclass(frozen=True, slots=True)
class OnlinePatchApplication:
    policy: ReleasePolicy
    patch_result: PatchResult
    executor: SimExecutor | None = field(default=None, repr=False)
    new_ready_tasks: tuple[str, ...] = ()
    directly_affected_tasks: tuple[str, ...] = ()
    released_tasks: tuple[str, ...] = ()
    preserved_active_assignments: dict[str, str] = field(default_factory=dict)
    before_assignments: dict[str, str] = field(default_factory=dict)
    after_assignments: dict[str, str] = field(default_factory=dict)
    assignment_changes: AssignmentChanges = field(default_factory=AssignmentChanges)
    consensus_rounds: tuple[int, ...] = ()

    @property
    def accepted(self) -> bool:
        return self.patch_result.accepted and self.executor is not None


def _active_assignments(executor: SimExecutor) -> dict[str, str]:
    return {
        task.task_id: task.assigned_agent
        for task in sorted(executor.graph.tasks, key=lambda item: item.task_id)
        if task.status in {TaskStatus.ASSIGNED, TaskStatus.RUNNING}
        and task.assigned_agent is not None
    }


def _eligible_bidders(executor: SimExecutor, task_id: str) -> frozenset[str]:
    task = executor.graph[task_id]
    return frozenset(
        aid
        for aid, agent in executor.agents.items()
        if agent.platform_kind in task.eligible_platforms
        and agent.has_capabilities(task.required_capabilities)
    )


def _directly_affected(
    executor: SimExecutor,
    new_ready: tuple[str, ...],
) -> tuple[str, ...]:
    new_bidders = set().union(
        *(_eligible_bidders(executor, task_id) for task_id in new_ready), set()
    )
    if not new_bidders:
        return ()
    return tuple(
        sorted(
            task.task_id
            for task in executor.graph.tasks
            if task.status is TaskStatus.ASSIGNED
            and task.task_id not in new_ready
            and _eligible_bidders(executor, task.task_id) & new_bidders
        )
    )


def _selective_suffix(
    executor: SimExecutor,
    directly_affected: tuple[str, ...],
) -> tuple[str, ...]:
    affected = set(directly_affected)
    released: set[str] = set()
    for aid in sorted(executor.agents):
        agent = executor.agents[aid]
        positions = [index for index, task_id in enumerate(agent.bundle) if task_id in affected]
        if not positions:
            continue
        suffix = agent.bundle[min(positions) :]
        for task_id in suffix:
            if executor.graph[task_id].status is TaskStatus.ASSIGNED:
                released.add(task_id)
    if not affected <= released:
        missing = sorted(affected - released)
        raise ValueError(f"affected assignments missing from owner bundle: {missing}")
    return tuple(sorted(released))


def _release_set(
    executor: SimExecutor,
    policy: ReleasePolicy,
    directly_affected: tuple[str, ...],
) -> tuple[str, ...]:
    if policy is ReleasePolicy.NO_RESET:
        return ()
    if policy is ReleasePolicy.FULL_RESET:
        return tuple(
            sorted(
                task.task_id
                for task in executor.graph.tasks
                if task.status is TaskStatus.ASSIGNED
            )
        )
    return _selective_suffix(executor, directly_affected)


def apply_online_patch(
    executor: SimExecutor,
    patch: MissionPatch,
    scene: Scene,
    *,
    policy: ReleasePolicy = ReleasePolicy.SELECTIVE,
) -> OnlinePatchApplication:
    """Apply, selectively release and rebid on a checkpoint clone.

    The caller's executor is never mutated.  A successful return owns a new
    executor that can replace the live runtime in one assignment (§19.4).
    """
    if not isinstance(policy, ReleasePolicy):
        raise ValueError("policy must be a ReleasePolicy")
    candidate = SimExecutor.from_checkpoint(executor.checkpoint(), scene)
    before = _active_assignments(candidate)
    patched, patch_result = apply_patch(candidate.work, patch, scene)
    if not patch_result.accepted:
        return OnlinePatchApplication(
            policy=policy,
            patch_result=patch_result,
            before_assignments=dict(sorted(before.items())),
            after_assignments=dict(sorted(before.items())),
        )

    candidate.replace_state(patched, scene)
    # Reconciliation may have released assignments because of a predecessor
    # diff.  Canonical P9 extensions currently produce none, but stale executor
    # winner records must still be removed if a future valid patch does.
    for task_id in patch_result.directly_released_tasks:
        candidate.assignments.pop(task_id, None)
        candidate.winning_bids.pop(task_id, None)

    added = set(patch_result.added_tasks)
    new_ready = tuple(
        sorted(
            task_id
            for task_id in added
            if candidate.graph[task_id].status is TaskStatus.READY
        )
    )
    affected = _directly_affected(candidate, new_ready)
    released = _release_set(candidate, policy, affected)
    if released:
        candidate.release_assignments(released)
    rounds = candidate.auction_ready()

    after = _active_assignments(candidate)
    all_released = set(released) | set(patch_result.directly_released_tasks)
    preserved = {
        task_id: agent_id
        for task_id, agent_id in before.items()
        if task_id not in all_released and after.get(task_id) == agent_id
    }
    return OnlinePatchApplication(
        policy=policy,
        patch_result=patch_result,
        executor=candidate,
        new_ready_tasks=new_ready,
        directly_affected_tasks=affected,
        released_tasks=released,
        preserved_active_assignments=dict(sorted(preserved.items())),
        before_assignments=dict(sorted(before.items())),
        after_assignments=dict(sorted(after.items())),
        assignment_changes=AssignmentChanges.between(before, after),
        consensus_rounds=rounds,
    )


__all__ = [
    "ONLINE_POLICY_VERSION",
    "AssignmentChanges",
    "OnlinePatchApplication",
    "ReleasePolicy",
    "apply_online_patch",
]
