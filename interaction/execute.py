"""Deterministic execution action for an operator planning session (§18.9).

Pressing run is not an LLM intent. It executes a clone through the existing
``SimExecutor``, stores the latest result, moves the session phase, and appends
one ``ExecutionAudit`` immediately. Graph, scene and plan-time analysis remain
unchanged.
"""

from datetime import datetime, timezone

from execution.executor import SimExecutor, Termination
from interaction.audit import ExecutionAudit
from interaction.mode import require_mode
from interaction.session import MissionSession, SessionPhase
from validator.hashing import graph_hash, scene_hash
from validator.patch import graph_edge_keys, graph_hash_nodes


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_graph_hash(session: MissionSession) -> str:
    graph = session.state.graph
    return graph_hash(graph_hash_nodes(graph), sorted(graph_edge_keys(graph)))


def _preconditions(session: MissionSession) -> None:
    if session.state is None or session.plan is None:
        raise ValueError("a committed mission and plan are required before execution")
    if session.pending_clarification is not None:
        raise ValueError("resolve or cancel the pending clarification before execution")
    if session.runtime is not None:
        raise ValueError("an online runtime cannot be executed through the one-shot action")
    if session.phase not in {SessionPhase.PLANNING, SessionPhase.EXECUTION_FAILED}:
        raise ValueError("an already completed session cannot be executed again")


def execute_session(session: MissionSession, *, mode: str) -> ExecutionAudit:
    """Execute the committed graph and append its audit event (D-032/D-033).

    Executor failures are results of the run action, so they are recorded and
    isolated. Invalid preconditions and provenance are caller wiring errors;
    those fail before an event or phase change is made.
    """
    checked_mode = require_mode(mode)
    _preconditions(session)
    pre_scene = scene_hash(session.scene)
    pre_graph = _state_graph_hash(session)
    plan_assignments = dict(sorted(session.plan.assignments.items()))
    started_at = _utc_now()

    try:
        result = SimExecutor(
            session.state,
            session.scene,
            active_agent_ids=session.active_team,
        ).run()
    except Exception as exc:  # noqa: BLE001 - a failed run must remain auditable
        finished_at = _utc_now()
        session.execution = None
        session.phase = SessionPhase.EXECUTION_FAILED
        audit = ExecutionAudit(
            session_id=session.session_id,
            pre_scene_hash=pre_scene,
            pre_graph_hash=pre_graph,
            plan_assignments=plan_assignments,
            execution_termination="ERROR",
            execution_assignments={},
            makespan=0.0,
            capability_violations=[],
            precedence_violations=[],
            mode=checked_mode,
            started_at=started_at,
            finished_at=finished_at,
            error_type=type(exc).__name__,
            error_detail=str(exc),
        )
        session.append_event(audit)
        return audit

    session.execution = result
    session.phase = (
        SessionPhase.EXECUTED
        if result.termination is Termination.COMPLETED
        else SessionPhase.EXECUTION_FAILED
    )
    audit = ExecutionAudit(
        session_id=session.session_id,
        pre_scene_hash=pre_scene,
        pre_graph_hash=pre_graph,
        plan_assignments=plan_assignments,
        execution_termination=result.termination.value,
        execution_assignments=dict(sorted(result.assignments.items())),
        makespan=result.makespan,
        capability_violations=list(result.capability_violations),
        precedence_violations=list(result.precedence_violations),
        mode=checked_mode,
        started_at=started_at,
        finished_at=_utc_now(),
    )
    session.append_event(audit)
    return audit


__all__ = ["execute_session"]
