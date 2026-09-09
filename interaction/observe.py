"""Apply a simulated FIRE_DETECTED observation through the §22.3 transaction.

Two entry points: :func:`apply_fire_observation` is the D-062-legacy auto path
(single ``SimulatedFireSource``, session policy), and the approval trio
:func:`enqueue_fire_approvals` / :func:`record_fire_decision` /
:func:`apply_recorded_fire_decisions` is the §22.8 operator gate for the
``SimulatedFireField`` path (D-065/D-066).  The operator's answer is recorded
during motion and applied only at the next task-completion boundary.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from allocation.allocate import AllocationResult, allocate
from allocation.online import OnlinePatchApplication, apply_online_patch
from core.enums import TaskType
from core.mission_state import MissionState
from interaction.audit import IncidentObservationAudit
from interaction.audit_builders import online_reallocation_audit, patch_audit
from interaction.incident_response import (
    PolicyOrigin,
    prepare_incident_transaction,
    publish_incident_transaction,
)
from interaction.mode import require_mode
from interaction.session import (
    ApprovalDecision,
    MissionSession,
    PendingFireApproval,
    ReferentKind,
)
from interaction.workflow import WORKFLOW_CHAIN
from scenarios.latent import FireDetectedObservation
from scenarios.scene import Scene
from validator.hashing import graph_hash, scene_hash
from validator.patch import graph_edge_keys, graph_hash_nodes

Planner = Callable[[MissionState, Scene], AllocationResult]
OnlineApplier = Callable[..., OnlinePatchApplication]


def _graph_hash(session: MissionSession) -> str | None:
    if session.state is None:
        return None
    graph = session.state.graph
    return graph_hash(graph_hash_nodes(graph), sorted(graph_edge_keys(graph)))


def _run_incident_transaction(
    session: MissionSession,
    *,
    fixture_id: str,
    zone_id: str,
    trigger_task_id: str,
    detecting_agent_id: str,
    simulation_time: float,
    response_up_to: TaskType | None,
    policy_origin: PolicyOrigin,
    mode: str,
    planner: Planner,
    online_applier: OnlineApplier,
) -> IncidentObservationAudit:
    """Run and audit one §22.3 incident transaction for a revealed fire.

    A failed validator/allocation/rebid attempt still creates an audit event,
    but never publishes the candidate incident or candidate mission objects.
    """
    checked_mode = require_mode(mode)
    pre_scene = scene_hash(session.scene)
    pre_graph = _graph_hash(session)
    transaction = None
    error = None
    outcome = "TURN_ERROR"
    try:
        transaction = prepare_incident_transaction(
            session,
            zone_id,
            response_up_to,
            planner=planner,
            online_applier=online_applier,
        )
        if not transaction.accepted:
            outcome = "REJECTED"
        else:
            publish_incident_transaction(session, transaction)
            session.note_referent(ReferentKind.INCIDENT, transaction.incident_id)
            outcome = "COMMITTED"
    except Exception as exc:  # noqa: BLE001 - observation failure must be auditable
        error = exc

    patch_result = transaction.patch_result if transaction is not None else None
    online = transaction.online if transaction is not None else None
    audit = IncidentObservationAudit(
        session_id=session.session_id,
        fixture_id=fixture_id,
        zone_id=zone_id,
        trigger_task_id=trigger_task_id,
        detecting_agent_id=detecting_agent_id,
        simulation_time=simulation_time,
        mode=checked_mode,
        outcome=outcome,
        incident_id=transaction.incident_id if transaction is not None else None,
        policy_origin=policy_origin.value,
        response_up_to=response_up_to.value if response_up_to is not None else None,
        pre_scene_hash=pre_scene,
        post_scene_hash=scene_hash(session.scene),
        pre_graph_hash=pre_graph,
        post_graph_hash=_graph_hash(session),
        pre_state_hash=patch_result.pre_state_hash if patch_result is not None else None,
        patch_hash=patch_result.patch_hash if patch_result is not None else None,
        patch=patch_audit(patch_result),
        online_reallocation=(
            online_reallocation_audit(online) if online is not None and online.accepted else None
        ),
        error_type=type(error).__name__ if error is not None else None,
        error_detail=str(error) if error is not None else None,
    )
    session.append_event(audit)
    return audit


def apply_fire_observation(
    session: MissionSession,
    observation: FireDetectedObservation,
    *,
    mode: str,
    planner: Planner = allocate,
    online_applier: OnlineApplier = apply_online_patch,
) -> IncidentObservationAudit:
    """D-062-legacy auto path: apply one revealed observation under session policy."""
    response_up_to = session.directive.incident_response_up_to
    origin = (
        PolicyOrigin.SESSION_POLICY if response_up_to is not None else PolicyOrigin.NONE
    )
    return _run_incident_transaction(
        session,
        fixture_id=observation.fixture_id,
        zone_id=observation.zone_id,
        trigger_task_id=observation.trigger_task_id,
        detecting_agent_id=observation.detecting_agent_id,
        simulation_time=observation.simulation_time,
        response_up_to=response_up_to,
        policy_origin=origin,
        mode=mode,
        planner=planner,
        online_applier=online_applier,
    )


def enqueue_fire_approvals(
    session: MissionSession,
    observations: tuple[FireDetectedObservation, ...],
    *,
    mode: str,
) -> tuple[IncidentObservationAudit, ...]:
    """§22.8 gate: hold revealed fires for the operator instead of auto-applying.

    ``observations`` arrive already zone-id ordered from ``SimulatedFireField``.
    Each one appends a ``PendingFireApproval`` to the session FIFO queue and an
    ``AWAITING_APPROVAL`` audit event.  Nothing touches the scene or graph.
    """
    checked_mode = require_mode(mode)
    scene = scene_hash(session.scene)
    graph = _graph_hash(session)
    audits = []
    pending = list(session.pending_approvals)
    for observation in observations:
        pending.append(
            PendingFireApproval(
                fixture_id=observation.fixture_id,
                zone_id=observation.zone_id,
                trigger_task_id=observation.trigger_task_id,
                detecting_agent_id=observation.detecting_agent_id,
                simulation_time=observation.simulation_time,
            )
        )
        audit = IncidentObservationAudit(
            session_id=session.session_id,
            fixture_id=observation.fixture_id,
            zone_id=observation.zone_id,
            trigger_task_id=observation.trigger_task_id,
            detecting_agent_id=observation.detecting_agent_id,
            simulation_time=observation.simulation_time,
            mode=checked_mode,
            outcome="AWAITING_APPROVAL",
            policy_origin=PolicyOrigin.NONE.value,
            pre_scene_hash=scene,
            post_scene_hash=scene,
            pre_graph_hash=graph,
            post_graph_hash=graph,
        )
        session.append_event(audit)
        audits.append(audit)
    session.pending_approvals = tuple(pending)
    return tuple(audits)


def record_fire_decision(
    session: MissionSession,
    *,
    decision: ApprovalDecision,
    response_up_to: TaskType | None = None,
) -> PendingFireApproval:
    """§22.8/D-066: record the operator's answer to the first undecided fire.

    Nothing is applied here — the decision is stamped onto the queue entry and
    applied at the next task-completion boundary by
    :func:`apply_recorded_fire_decisions`.  APPROVE needs a workflow scope.
    """
    if not isinstance(decision, ApprovalDecision):
        raise ValueError("decision must be an ApprovalDecision")
    if decision is ApprovalDecision.APPROVE and (
        response_up_to is None or response_up_to not in WORKFLOW_CHAIN
    ):
        raise ValueError("approving a fire needs a workflow scope")

    pending = list(session.pending_approvals)
    index = next(
        (i for i, item in enumerate(pending) if not item.decided), None
    )
    if index is None:
        raise ValueError("no undecided fire approval is pending")
    decided = replace(
        pending[index],
        decision=decision,
        approved_scope=response_up_to if decision is ApprovalDecision.APPROVE else None,
    )
    pending[index] = decided
    session.pending_approvals = tuple(pending)
    return decided


def _decline_audit(session: MissionSession, item: PendingFireApproval, mode: str):
    scene = scene_hash(session.scene)
    graph = _graph_hash(session)
    audit = IncidentObservationAudit(
        session_id=session.session_id,
        fixture_id=item.fixture_id,
        zone_id=item.zone_id,
        trigger_task_id=item.trigger_task_id,
        detecting_agent_id=item.detecting_agent_id,
        simulation_time=item.simulation_time,
        mode=require_mode(mode),
        outcome="DECLINED",
        policy_origin=PolicyOrigin.NONE.value,
        pre_scene_hash=scene,
        post_scene_hash=scene,
        pre_graph_hash=graph,
        post_graph_hash=graph,
    )
    session.append_event(audit)
    return audit


def apply_recorded_fire_decisions(
    session: MissionSession,
    *,
    mode: str,
    planner: Planner = allocate,
    online_applier: OnlineApplier = apply_online_patch,
) -> tuple[IncidentObservationAudit, ...]:
    """§22.8/D-066: at a boundary, apply the decided fires in FIFO order.

    Stops at the first still-undecided entry so the queue order is preserved.
    APPROVE runs the §22.3 transaction (``PolicyOrigin.EXPLICIT``); DECLINE
    only records a ``DECLINED`` audit.  Nothing happens for an undecided head.
    """
    audits = []
    while session.pending_approvals and session.pending_approvals[0].decided:
        head, *rest = session.pending_approvals
        session.pending_approvals = tuple(rest)
        if head.decision is ApprovalDecision.DECLINE:
            audits.append(_decline_audit(session, head, mode))
            continue
        audits.append(
            _run_incident_transaction(
                session,
                fixture_id=head.fixture_id,
                zone_id=head.zone_id,
                trigger_task_id=head.trigger_task_id,
                detecting_agent_id=head.detecting_agent_id,
                simulation_time=head.simulation_time,
                response_up_to=head.approved_scope,
                policy_origin=PolicyOrigin.EXPLICIT,
                mode=mode,
                planner=planner,
                online_applier=online_applier,
            )
        )
    return tuple(audits)


def has_undecided_fire(session: MissionSession) -> bool:
    return any(not item.decided for item in session.pending_approvals)


__all__ = [
    "ApprovalDecision",
    "apply_fire_observation",
    "apply_recorded_fire_decisions",
    "enqueue_fire_approvals",
    "has_undecided_fire",
    "record_fire_decision",
]
