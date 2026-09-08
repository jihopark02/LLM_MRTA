"""One atomic path for operator-reported and simulated-sensor incidents (§22.3).

This module prepares a complete candidate without mutating the live session.
The caller publishes that candidate only after registration, patch validation,
and either plan-time allocation or paused-runtime release/rebid have all
succeeded.  Operator and sensor entry points therefore cannot drift into two
different adaptation algorithms.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from allocation.allocate import AllocationResult
from allocation.online import OnlinePatchApplication, ReleasePolicy
from core.enums import TaskType
from core.mission_state import MissionState
from execution.executor import SimExecutor, Termination
from interaction.ground import build_chain_patch
from interaction.scene_mut import register_incident
from interaction.session import MissionSession, SessionPhase
from interaction.workflow import WORKFLOW_CHAIN
from scenarios.scene import Scene
from validator.patch_apply import PatchResult, apply_patch


class IncidentSource(str, Enum):
    OPERATOR = "OPERATOR"
    SENSOR_SIMULATED = "SENSOR_SIMULATED"


class PolicyOrigin(str, Enum):
    EXPLICIT = "EXPLICIT"
    SESSION_POLICY = "SESSION_POLICY"
    NONE = "NONE"


@dataclass(frozen=True, slots=True)
class IncidentTransaction:
    """A prepared, not-yet-published incident adaptation."""

    scene: Scene
    incident_id: str
    zone_id: str
    response_up_to: TaskType | None
    state: MissionState | None
    plan: AllocationResult | None
    runtime: SimExecutor | None
    patch_result: PatchResult | None = None
    online: OnlinePatchApplication | None = None

    @property
    def accepted(self) -> bool:
        if self.online is not None:
            return self.online.accepted
        return self.patch_result is None or self.patch_result.accepted


def completed_online_terminal(session: MissionSession) -> bool:
    """Whether D-055 may start a follow-on response from this checkpoint."""
    return (
        session.phase is SessionPhase.EXECUTED
        and session.runtime is not None
        and session.execution is not None
        and session.execution.termination is Termination.COMPLETED
    )


def publish_incident_transaction(
    session: MissionSession, transaction: IncidentTransaction
) -> None:
    """Publish one fully prepared transaction without another computation."""
    if not transaction.accepted:
        raise ValueError("cannot publish a rejected incident transaction")
    if (
        session.phase is SessionPhase.EXECUTED
        and transaction.online is None
        and transaction.runtime is None
    ):
        raise ValueError("follow-on report has no preserved online runtime")
    session.scene = transaction.scene
    if transaction.online is not None:
        follow_on = session.phase is SessionPhase.EXECUTED
        session.runtime = transaction.runtime
        session.state = transaction.state
        if follow_on:
            # The previous ExecutionAudit stays in the append-only event log;
            # these fields now describe the newly opened response episode.
            session.execution = None
            session.online_started_at = None
            session.phase = SessionPhase.EXECUTION_PAUSED
    elif transaction.response_up_to is not None:
        session.state, session.plan = transaction.state, transaction.plan
    elif session.phase in {SessionPhase.EXECUTION_PAUSED, SessionPhase.EXECUTED}:
        # A scene-only report keeps the checkpoint identity/clock. The scene is
        # immutable data used by subsequent patches and views.
        if session.runtime is None:
            raise ValueError("online session has no runtime")
        session.runtime.scene = transaction.scene


Planner = Callable[[MissionState, Scene], AllocationResult]
OnlineApplier = Callable[..., OnlinePatchApplication]


def prepare_incident_transaction(
    session: MissionSession,
    zone_id: str,
    response_up_to: TaskType | None,
    *,
    planner: Planner,
    online_applier: OnlineApplier,
) -> IncidentTransaction:
    """Build the §22.3 candidate while preserving every live object.

    ``response_up_to=None`` is the deliberately scene-only legacy behaviour.
    A response workflow requires an active mission; callers turn that case
    into a clarification before invoking this function.
    """
    if response_up_to is not None and response_up_to not in WORKFLOW_CHAIN:
        raise ValueError(f"not an incident workflow step: {response_up_to!r}")
    if response_up_to is not None and session.state is None:
        raise ValueError("an incident response requires an active mission")
    if session.phase is SessionPhase.EXECUTED and not completed_online_terminal(session):
        raise ValueError("follow-on response requires a completed online terminal")

    candidate_scene, incident_id = register_incident(session.scene, zone_id)
    if response_up_to is None:
        return IncidentTransaction(
            scene=candidate_scene,
            incident_id=incident_id,
            zone_id=zone_id,
            response_up_to=None,
            state=session.state,
            plan=session.plan,
            runtime=session.runtime,
        )

    chain = build_chain_patch(session.state.graph, incident_id, response_up_to)
    if chain.no_change or chain.patch is None:
        raise ValueError("a newly registered incident unexpectedly produced no patch")

    if session.phase in {SessionPhase.EXECUTION_PAUSED, SessionPhase.EXECUTED}:
        if session.runtime is None:
            raise ValueError("online session has no runtime")
        online = online_applier(
            session.runtime,
            chain.patch,
            candidate_scene,
            policy=ReleasePolicy.SELECTIVE,
        )
        return IncidentTransaction(
            scene=candidate_scene,
            incident_id=incident_id,
            zone_id=zone_id,
            response_up_to=response_up_to,
            state=online.executor.work if online.accepted else session.state,
            plan=session.plan,
            runtime=online.executor if online.accepted else session.runtime,
            patch_result=online.patch_result,
            online=online,
        )

    if session.phase is not SessionPhase.PLANNING:
        raise ValueError(f"incident transaction is not allowed in {session.phase.value}")

    candidate_state, patch_result = apply_patch(
        session.state, chain.patch, candidate_scene
    )
    if not patch_result.accepted:
        return IncidentTransaction(
            scene=candidate_scene,
            incident_id=incident_id,
            zone_id=zone_id,
            response_up_to=response_up_to,
            state=session.state,
            plan=session.plan,
            runtime=session.runtime,
            patch_result=patch_result,
        )
    candidate_plan = planner(candidate_state, candidate_scene)
    return IncidentTransaction(
        scene=candidate_scene,
        incident_id=incident_id,
        zone_id=zone_id,
        response_up_to=response_up_to,
        state=candidate_state,
        plan=candidate_plan,
        runtime=session.runtime,
        patch_result=patch_result,
    )


__all__ = [
    "IncidentSource",
    "PolicyOrigin",
    "IncidentTransaction",
    "completed_online_terminal",
    "prepare_incident_transaction",
    "publish_incident_transaction",
]
