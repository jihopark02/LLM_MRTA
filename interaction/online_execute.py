"""Checkpoint-driven execution actions for online operator interaction (§19)."""

from datetime import datetime, timezone

from core.enums import TaskStatus
from execution.executor import ExecutionResult, SimExecutor, Termination
from interaction.audit import CheckpointAudit, ExecutionAudit
from interaction.mode import require_mode
from interaction.session import MissionSession, SessionPhase
from validator.hashing import graph_hash, scene_hash
from validator.patch import graph_edge_keys, graph_hash_nodes


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _graph_hash(session: MissionSession) -> str:
    graph = session.state.graph
    return graph_hash(graph_hash_nodes(graph), sorted(graph_edge_keys(graph)))


#: §19.1. PLANNING starts a run; PAUSED continues one; EXECUTION_FAILED is a
#: retry, but only while the last good runtime survived the failure (D-041).
_RESUMABLE = {SessionPhase.EXECUTION_PAUSED, SessionPhase.EXECUTION_FAILED}


def _preconditions(session: MissionSession) -> None:
    if session.state is None or session.plan is None:
        raise ValueError("a committed mission and plan are required before online execution")
    if session.pending_clarification is not None:
        raise ValueError("resolve or cancel the pending clarification before execution")
    if session.phase not in {SessionPhase.PLANNING} | _RESUMABLE:
        raise ValueError("online execution can start, continue or retry only before completion")
    if session.phase is SessionPhase.PLANNING and session.runtime is not None:
        raise ValueError("a planning session cannot already own an online runtime")
    if session.phase in _RESUMABLE and session.runtime is None:
        # An EXECUTION_FAILED without a runtime is a one-shot failure; §18.1
        # sends that back through execute_session, not through here.
        raise ValueError("resuming online execution requires the preserved runtime")


def _active_assignments(executor: SimExecutor) -> dict[str, str]:
    return {
        task.task_id: task.assigned_agent
        for task in sorted(executor.graph.tasks, key=lambda item: item.task_id)
        if task.status in {TaskStatus.ASSIGNED, TaskStatus.RUNNING}
        and task.assigned_agent is not None
    }


def _checkpoint_audit(
    session: MissionSession,
    executor: SimExecutor,
    completed_now: tuple[str, ...],
    mode: str,
) -> CheckpointAudit:
    running = {
        sim.current: {
            "agent_id": agent_id,
            "finish_time": sim.finish_at,
        }
        for agent_id, sim in sorted(executor.sim.items())
        if sim.current is not None
    }
    return CheckpointAudit(
        session_id=session.session_id,
        simulation_time=executor.now,
        completed_now=list(completed_now),
        completed=sorted(
            task.task_id
            for task in executor.graph.tasks
            if task.status is TaskStatus.COMPLETED
        ),
        running=running,
        ready_tasks=sorted(executor.graph.ids_with_status(TaskStatus.READY)),
        active_assignments=_active_assignments(executor),
        mode=mode,
    )


def _execution_audit(
    session: MissionSession,
    result: ExecutionResult | None,
    *,
    mode: str,
    started_at: str,
    error: BaseException | None = None,
) -> ExecutionAudit:
    return ExecutionAudit(
        session_id=session.session_id,
        pre_scene_hash=scene_hash(session.scene),
        pre_graph_hash=_graph_hash(session),
        plan_assignments=dict(sorted(session.plan.assignments.items())),
        execution_termination=(result.termination.value if result else "ERROR"),
        execution_assignments=(
            dict(sorted(result.assignments.items())) if result else {}
        ),
        makespan=result.makespan if result else 0.0,
        capability_violations=list(result.capability_violations) if result else [],
        precedence_violations=list(result.precedence_violations) if result else [],
        mode=mode,
        started_at=started_at,
        finished_at=_utc_now(),
        error_type=type(error).__name__ if error else None,
        error_detail=str(error) if error else None,
    )


def advance_online_session(
    session: MissionSession,
    *,
    mode: str,
) -> CheckpointAudit | ExecutionAudit:
    """Start, advance or retry online execution by one completion event.

    Work is performed on a new executor.  The session's runtime/state pair is
    replaced only after a successful advance, so an exception cannot leave a
    half-advanced clock or task status behind (§19.4).

    A failed advance keeps the last good runtime, so calling this again retries
    from that checkpoint (§19.1, D-041) — the counterpart of §18.1's one-shot
    "retry the same graph".  Retrying resumes the same run: it does not rewind
    simulation time or the completed prefix.
    """
    checked_mode = require_mode(mode)
    _preconditions(session)
    started_at = session.online_started_at or _utc_now()

    if session.phase is SessionPhase.PLANNING:
        candidate = SimExecutor(session.state, session.scene)
    else:
        candidate = SimExecutor.from_checkpoint(session.runtime.checkpoint(), session.scene)

    try:
        advance = candidate.advance_to_next_completion()
    except Exception as exc:  # noqa: BLE001 - execution failures are audit events
        audit = _execution_audit(
            session,
            None,
            mode=checked_mode,
            started_at=started_at,
            error=exc,
        )
        session.execution = None
        session.phase = SessionPhase.EXECUTION_FAILED
        session.append_event(audit)
        return audit

    # Atomic runtime/state publication after the candidate has advanced.
    session.runtime = candidate
    session.state = candidate.work
    session.online_started_at = started_at

    if advance.execution is None:
        session.phase = SessionPhase.EXECUTION_PAUSED
        audit = _checkpoint_audit(
            session, candidate, advance.completed_now, checked_mode
        )
        session.append_event(audit)
        return audit

    result = advance.execution
    session.execution = result
    session.phase = (
        SessionPhase.EXECUTED
        if result.termination is Termination.COMPLETED
        else SessionPhase.EXECUTION_FAILED
    )
    audit = _execution_audit(
        session,
        result,
        mode=checked_mode,
        started_at=started_at,
    )
    session.online_started_at = None
    session.append_event(audit)
    return audit


__all__ = ["advance_online_session"]
