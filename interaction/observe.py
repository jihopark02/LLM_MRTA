"""Apply a simulated FIRE_DETECTED observation through the §22.3 transaction."""

from __future__ import annotations

from collections.abc import Callable

from allocation.allocate import AllocationResult, allocate
from allocation.online import OnlinePatchApplication, apply_online_patch
from core.mission_state import MissionState
from interaction.audit import IncidentObservationAudit
from interaction.audit_builders import online_reallocation_audit, patch_audit
from interaction.incident_response import (
    PolicyOrigin,
    prepare_incident_transaction,
    publish_incident_transaction,
)
from interaction.mode import require_mode
from interaction.session import MissionSession, ReferentKind
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


def apply_fire_observation(
    session: MissionSession,
    observation: FireDetectedObservation,
    *,
    mode: str,
    planner: Planner = allocate,
    online_applier: OnlineApplier = apply_online_patch,
) -> IncidentObservationAudit:
    """Record and atomically apply one already-revealed simulated observation.

    A failed validator/allocation/rebid attempt still creates an audit event,
    but never publishes the candidate incident or candidate mission objects.
    """
    checked_mode = require_mode(mode)
    pre_scene = scene_hash(session.scene)
    pre_graph = _graph_hash(session)
    response_up_to = session.directive.incident_response_up_to
    origin = (
        PolicyOrigin.SESSION_POLICY if response_up_to is not None else PolicyOrigin.NONE
    )
    transaction = None
    error = None
    outcome = "TURN_ERROR"
    try:
        transaction = prepare_incident_transaction(
            session,
            observation.zone_id,
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
        fixture_id=observation.fixture_id,
        zone_id=observation.zone_id,
        trigger_task_id=observation.trigger_task_id,
        detecting_agent_id=observation.detecting_agent_id,
        simulation_time=observation.simulation_time,
        mode=checked_mode,
        outcome=outcome,
        incident_id=transaction.incident_id if transaction is not None else None,
        policy_origin=origin.value,
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


__all__ = ["apply_fire_observation"]
