"""Shared conversion of validator/allocation results into interaction audits."""

from allocation.online import ONLINE_POLICY_VERSION, OnlinePatchApplication
from interaction.audit import (
    OnlineReallocationAudit,
    PatchAudit,
    ResolvedClauseAudit,
    RuntimeAssignmentChanges,
    SemanticIRAudit,
)
from interaction.ground import GroundingOutcome
from interaction.mission_ir import IncidentSelector, SemanticMissionIR, ZoneSelector
from interaction.resolve import ResolvedMissionIR
from validator.patch_apply import PatchResult


def _zone_operator(sel: ZoneSelector) -> str:
    if sel.explicit:
        base = f"EXPLICIT({', '.join(sel.explicit)})"
    elif sel.region is not None:
        base = f"REGION({sel.region})"
    else:
        base = f"RANGE({sel.range_from}..{sel.range_to})"
    if sel.exclude:
        base += f" EXCLUDE({', '.join(sel.exclude)})"
    if sel.unvisited_only:
        base += " UNVISITED_ONLY"
    return base


def _incident_operator(sel: IncidentSelector) -> str:
    if sel.explicit:
        base = f"EXPLICIT({', '.join(sel.explicit)})"
    elif sel.deixis is not None:
        base = f"DEIXIS({sel.deixis})"
    elif sel.recency == "ALL_KNOWN":
        base = "ALL_KNOWN"
    else:
        parts = [sel.recency]
        if sel.recent_count is not None:
            parts.append(f"n={sel.recent_count}")
        if sel.recent_source is not None:
            parts.append(sel.recent_source)
        base = f"RECENT({', '.join(parts)})"
    if sel.spatial_pick is not None:
        base += f" {sel.spatial_pick}"
    return base


def semantic_ir_audit(
    ir: SemanticMissionIR, resolved: ResolvedMissionIR | GroundingOutcome
) -> SemanticIRAudit:
    """D-076 provenance: the emitted IR plus, per clause, the operator label and
    the ids it resolved to. On a fail-closed resolver clarification only the
    reason is recorded — there is no partial resolution."""
    if isinstance(resolved, GroundingOutcome):
        return SemanticIRAudit(
            ir=ir.model_dump(),
            clarification_reason=resolved.reason.value if resolved.reason else None,
        )
    return SemanticIRAudit(
        ir=ir.model_dump(),
        recon=[
            ResolvedClauseAudit(_zone_operator(clause.zones), list(out.zone_ids))
            for clause, out in zip(ir.recon, resolved.recon, strict=True)
        ],
        responses=[
            ResolvedClauseAudit(
                f"{_incident_operator(clause.incidents)} -> {out.response_up_to}",
                list(out.incident_ids),
            )
            for clause, out in zip(ir.responses, resolved.responses, strict=True)
        ],
    )


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


__all__ = ["online_reallocation_audit", "patch_audit", "semantic_ir_audit"]
