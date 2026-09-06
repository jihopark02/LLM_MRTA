"""P9.3 gate: paused natural-language turns and typed online audit (§19.4)."""

from pathlib import Path

import pytest

from allocation.allocate import allocate
from interaction.audit import CheckpointAudit, ExecutionAudit
from interaction.audit_io import session_audit_payload
from interaction.online_execute import advance_online_session
from interaction.orchestrator import TurnOutcome, handle_turn
from interaction.schemas import wire_intent
from interaction.session import (
    MissionSession,
    PendingClarification,
    ReferentKind,
    SessionPhase,
    fresh_session_state,
)
from llm.backend import MockBackend
from scenarios.fixture import load_reference_fixture
from scenarios.scene import load_scene
from validator.hashing import graph_hash, pre_state_hash
from validator.patch import graph_edge_keys, graph_hash_nodes

SCENARIOS = Path(__file__).parents[1] / "scenarios"


@pytest.fixture
def planned_session():
    scene = load_scene(SCENARIOS / "industrial_park.yaml")
    graph = load_reference_fixture().graph
    state = fresh_session_state(graph, scene)
    return MissionSession("ONLINE", scene, state=state, plan=allocate(state, scene))


def _runtime_signature(runtime):
    checkpoint = runtime.checkpoint()
    work = checkpoint._work
    return (
        graph_hash(graph_hash_nodes(work.graph), sorted(graph_edge_keys(work.graph))),
        pre_state_hash(work),
        checkpoint.now,
        checkpoint.access_nodes,
        checkpoint.sim,
        checkpoint.assignments,
        checkpoint.winning_bids,
        checkpoint.task_departure,
        checkpoint.task_start,
        checkpoint.task_completion,
        checkpoint.consensus_rounds,
        checkpoint.uav_flight,
        checkpoint.ugv_route,
        checkpoint.started,
        checkpoint.epoch_pending,
    )


def _turn(session, utterance, kind, **slots):
    return handle_turn(
        session,
        utterance,
        MockBackend([wire_intent(kind, **slots)]),
    )


def test_online_start_pauses_after_one_completion_without_consuming_a_turn(
    planned_session,
):
    audit = advance_online_session(planned_session, mode="mock")

    assert isinstance(audit, CheckpointAudit)
    assert planned_session.phase is SessionPhase.EXECUTION_PAUSED
    assert planned_session.runtime is not None
    assert planned_session.state is planned_session.runtime.work
    assert planned_session.turn_count == 0
    assert audit.simulation_time == planned_session.runtime.now
    assert audit.completed_now
    assert audit.completed
    assert audit.running
    assert audit.active_assignments
    assert audit.event_type == "EXECUTION_CHECKPOINT"


def test_repeated_online_continue_finishes_and_preserves_event_order(planned_session):
    while planned_session.phase is not SessionPhase.EXECUTED:
        advance_online_session(planned_session, mode="mock")

    assert planned_session.execution is not None
    assert len(planned_session.execution.completed) == 12
    assert planned_session.execution.capability_violations == []
    assert planned_session.execution.precedence_violations == []
    assert all(isinstance(event, CheckpointAudit) for event in planned_session.event_log[:-1])
    assert isinstance(planned_session.event_log[-1], ExecutionAudit)
    payload = session_audit_payload(planned_session)
    assert [event["event_seq"] for event in payload["events"]] == list(
        range(len(payload["events"]))
    )


def test_paused_report_then_update_replaces_only_the_accepted_runtime(planned_session):
    advance_online_session(planned_session, mode="mock")
    runtime_before_report = planned_session.runtime
    time_before_report = runtime_before_report.now

    report = _turn(
        planned_session,
        "A 구역에 새 화재가 발생했어",
        "REPORT_INCIDENT",
        zone_ref="A 구역",
    )
    assert report.outcome is TurnOutcome.COMMITTED
    assert planned_session.phase is SessionPhase.EXECUTION_PAUSED
    assert planned_session.runtime is runtime_before_report
    assert planned_session.runtime.now == time_before_report
    assert "FIRE_SITE_3" in planned_session.scene.incidents

    old_runtime = planned_session.runtime
    old_signature = _runtime_signature(old_runtime)
    locked = {
        task.task_id: (task.status.value, task.assigned_agent)
        for task in old_runtime.graph.tasks
        if task.status.value in {"COMPLETED", "RUNNING"}
    }
    update = _turn(
        planned_session,
        "거기 지상 진압까지 추가해줘",
        "UPDATE_MISSION",
        target_phrase="거기",
        up_to_step="GROUND_SUPPRESSION",
    )

    assert update.outcome is TurnOutcome.COMMITTED
    assert update.audit.online_reallocation is not None
    assert update.audit.online_reallocation.policy == "selective"
    assert update.audit.online_reallocation.patch_added_tasks
    assert update.audit.online_reallocation.selectively_released_tasks
    assert planned_session.runtime is not old_runtime
    assert planned_session.state is planned_session.runtime.work
    assert _runtime_signature(old_runtime) == old_signature
    assert {
        task.task_id: (task.status.value, task.assigned_agent)
        for task in planned_session.runtime.graph.tasks
        if task.status.value in {"COMPLETED", "RUNNING"}
    } == locked

    while planned_session.phase is SessionPhase.EXECUTION_PAUSED:
        advance_online_session(planned_session, mode="mock")
    assert planned_session.phase is SessionPhase.EXECUTED
    assert len(planned_session.execution.completed) == 16
    assert planned_session.execution.capability_violations == []
    assert planned_session.execution.precedence_violations == []


def test_paused_query_reads_runtime_without_changing_it(planned_session):
    advance_online_session(planned_session, mode="mock")
    runtime = planned_session.runtime
    signature = _runtime_signature(runtime)

    result = _turn(planned_session, "현재 상태", "QUERY_STATUS", about="mission")

    assert result.outcome is TurnOutcome.ANSWERED
    assert "실행 일시정지" in result.message
    assert planned_session.runtime is runtime
    assert _runtime_signature(runtime) == signature


def test_paused_no_change_does_not_replace_runtime(planned_session):
    advance_online_session(planned_session, mode="mock")
    runtime = planned_session.runtime
    signature = _runtime_signature(runtime)

    result = _turn(
        planned_session,
        "FIRE_SITE_1 지상 진압까지",
        "UPDATE_MISSION",
        target_phrase="FIRE_SITE_1",
        up_to_step="GROUND_SUPPRESSION",
    )

    assert result.outcome is TurnOutcome.NO_CHANGE
    assert result.audit.online_reallocation is None
    assert planned_session.runtime is runtime
    assert _runtime_signature(runtime) == signature


def test_online_update_exception_preserves_runtime_state_and_scene(
    planned_session, monkeypatch
):
    from interaction import orchestrator

    advance_online_session(planned_session, mode="mock")
    _turn(
        planned_session,
        "A 구역에 새 화재",
        "REPORT_INCIDENT",
        zone_ref="A 구역",
    )
    runtime, state, scene = (
        planned_session.runtime,
        planned_session.state,
        planned_session.scene,
    )
    signature = _runtime_signature(runtime)
    monkeypatch.setattr(
        orchestrator,
        "apply_online_patch",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("rebid boom")),
    )

    result = _turn(
        planned_session,
        "거기 진압까지",
        "UPDATE_MISSION",
        target_phrase="거기",
        up_to_step="GROUND_SUPPRESSION",
    )

    assert result.outcome is TurnOutcome.TURN_ERROR
    assert planned_session.runtime is runtime
    assert planned_session.state is state
    assert planned_session.scene is scene
    assert _runtime_signature(runtime) == signature


def test_paused_clarification_preserves_runtime(planned_session):
    advance_online_session(planned_session, mode="mock")
    runtime = planned_session.runtime
    signature = _runtime_signature(runtime)

    result = _turn(
        planned_session,
        "그 화재 진압까지",
        "UPDATE_MISSION",
        target_phrase="그 화재",
        up_to_step="GROUND_SUPPRESSION",
    )

    assert result.outcome is TurnOutcome.CLARIFICATION
    assert planned_session.pending_clarification is not None
    assert planned_session.runtime is runtime
    assert _runtime_signature(runtime) == signature


def test_paused_validator_rejection_preserves_runtime(planned_session, monkeypatch):
    from core.enums import TaskType
    from interaction import orchestrator
    from interaction.ground import PatchPlan
    from validator.patch import AddEdge, MissionPatch

    advance_online_session(planned_session, mode="mock")
    runtime = planned_session.runtime
    signature = _runtime_signature(runtime)

    def invalid_patch(graph, incident_id, up_to_step):
        return PatchPlan(
            patch=MissionPatch(
                [
                    AddEdge(
                        (TaskType.THERMAL_RECON, "FIRE_SITE_1"),
                        (TaskType.THERMAL_RECON, "FIRE_SITE_2"),
                    )
                ]
            ),
            note="invalid",
        )

    monkeypatch.setattr(orchestrator, "build_chain_patch", invalid_patch)
    result = _turn(
        planned_session,
        "FIRE_SITE_1 진압까지",
        "UPDATE_MISSION",
        target_phrase="FIRE_SITE_1",
        up_to_step="GROUND_SUPPRESSION",
    )

    assert result.outcome is TurnOutcome.REJECTED
    assert result.patch_result is not None and not result.patch_result.accepted
    assert planned_session.runtime is runtime
    assert _runtime_signature(runtime) == signature


def test_pending_clarification_blocks_online_continue(planned_session):
    planned_session.pending_clarification = PendingClarification(
        source_turn_id="t1",
        intent_kind="UPDATE_MISSION",
        extracted_slots={
            "target_phrase": "그 화재",
            "up_to_step": "GROUND_SUPPRESSION",
        },
        unresolved_slot="target_phrase",
        entity_kind=ReferentKind.INCIDENT,
        candidates=("FIRE_SITE_1", "FIRE_SITE_2"),
        original_utterance="그 화재 진압까지",
    )

    with pytest.raises(ValueError, match="pending clarification"):
        advance_online_session(planned_session, mode="mock")
    assert planned_session.phase is SessionPhase.PLANNING
    assert planned_session.runtime is None
    assert planned_session.event_log == ()
