"""Shared conversion of validator/allocation results into interaction audits."""

from allocation.online import ONLINE_POLICY_VERSION, OnlinePatchApplication
from interaction.audit import (
    OnlineReallocationAudit,
    PatchAudit,
    RuntimeAssignmentChanges,
)
from validator.patch_apply import PatchResult


def patch_audit(result: PatchResult | None) -> PatchAudit | None:
    if result is None:
        return None
    return PatchAudit(
        accepted=result.accepted,
        error_codes=[code.value for code in result.error_codes],
        added_tasks=list(result.added_tasks),
        added_edges=[list(edge) for edge in result.added_edges],
        directly_released_tasks=list(result.directly_released_tasks),
        status_changes=[list(change) for change in result.status_changes],
    )


def online_reallocation_audit(
    result: OnlinePatchApplication,
) -> OnlineReallocationAudit:
    changes = result.assignment_changes
    return OnlineReallocationAudit(
        policy=result.policy.value,
        policy_version=ONLINE_POLICY_VERSION,
        simulation_time=result.executor.now,
        patch_added_tasks=list(result.patch_result.added_tasks),
        directly_affected_tasks=list(result.directly_affected_tasks),
        selectively_released_tasks=list(result.released_tasks),
        preserved_active_assignments=dict(result.preserved_active_assignments),
        before_assignments=dict(result.before_assignments),
        after_assignments=dict(result.after_assignments),
        assignment_changes=RuntimeAssignmentChanges(
            added=dict(changes.added),
            removed=dict(changes.removed),
            changed={task: list(owners) for task, owners in changes.changed.items()},
        ),
        consensus_rounds=list(result.consensus_rounds),
    )


__all__ = ["online_reallocation_audit", "patch_audit"]
