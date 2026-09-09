"""P9.3 gate: paused natural-language turns and typed online audit (§19.4)."""

from contextlib import contextmanager
from pathlib import Path

import pytest

from allocation.allocate import allocate
from execution.executor import CompletionAdvance, SimExecutor, Termination
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
    assert len(planned_session.execution.completed) == 8
    assert planned_session.execution.capability_violations == []
    assert planned_session.execution.precedence_violations == []
    assert all(isinstance(event, CheckpointAudit) for event in planned_session.event_log[:-1])
    assert isinstance(planned_session.event_log[-1], ExecutionAudit)
    payload = session_audit_payload(planned_session)
    assert [event["event_seq"] for event in payload["events"]] == list(
        range(len(payload["events"]))
    )


def test_completed_online_run_accepts_one_turn_follow_on_response(planned_session):
    while planned_session.phase is not SessionPhase.EXECUTED:
        advance_online_session(planned_session, mode="mock")

    terminal_runtime = planned_session.runtime
    terminal_time = terminal_runtime.now
    completed_before = {
        task.task_id
        for task in terminal_runtime.graph.tasks
        if task.status.value == "COMPLETED"
    }
    assert len(completed_before) == 8
    assert isinstance(planned_session.event_log[-1], ExecutionAudit)

    result = _turn(
        planned_session,
        "A 구역에 새 화재가 발생했어. 지상 진압까지 대응해줘",
        "REPORT_INCIDENT",
        zone_ref="A 구역",
        response_up_to="GROUND_SUPPRESSION",
    )

    assert result.outcome is TurnOutcome.COMMITTED
    assert result.audit.online_reallocation is not None
    assert planned_session.phase is SessionPhase.EXECUTION_PAUSED
    assert planned_session.execution is None
    assert planned_session.runtime is not terminal_runtime
    assert planned_session.runtime.now == terminal_time
    assert completed_before == {
        task.task_id
        for task in planned_session.runtime.graph.tasks
        if task.status.value == "COMPLETED"
    }
    added = {
        task.task_id
        for task in planned_session.runtime.graph.tasks
        if task.target == "FIRE_SITE_3"
    }
    assert len(added) == 2

    while planned_session.phase is SessionPhase.EXECUTION_PAUSED:
        advance_online_session(planned_session, mode="mock")

    assert planned_session.phase is SessionPhase.EXECUTED
    assert planned_session.execution.termination is Termination.COMPLETED
    assert not planned_session.execution.capability_violations
    assert not planned_session.execution.precedence_violations
    event_types = [event.event_type for event in planned_session.event_log]
    first_execution = event_types.index("EXECUTION")
    assert event_types[first_execution + 1] == "TURN"
    assert event_types[-1] == "EXECUTION"
    assert event_types.count("EXECUTION") == 2


def test_completed_run_accepts_a_new_mission_episode_from_current_positions(
    planned_session,
):
    from llm.schemas import LLMTask, Step1Output, Step2Output

    while planned_session.phase is not SessionPhase.EXECUTED:
        advance_online_session(planned_session, mode="mock")
    assert isinstance(planned_session.event_log[-1], ExecutionAudit)
    uav_end = {
        aid: agent.position
        for aid, agent in planned_session.runtime.agents.items()
        if agent.platform_kind.name == "UAV"
    }
    assert uav_end  # UAVs finished somewhere other than their scene start

    zones = sorted(planned_session.scene.zones)
    backend = MockBackend(
        [
            wire_intent("NEW_MISSION"),
            Step1Output(tasks=[LLMTask(task_type="AREA_RECON", target=z) for z in zones]),
            Step2Output(edges=[]),
        ]
    )
    result = handle_turn(planned_session, "전체 구역 다시 정찰해줘", backend)

    assert result.outcome is TurnOutcome.COMMITTED
    assert planned_session.phase is SessionPhase.PLANNING  # a fresh episode
    assert planned_session.runtime is None
    assert planned_session.execution is None
    assert len(planned_session.state.graph) == len(zones)
    assert {t.task_type.value for t in planned_session.state.graph.tasks} == {"AREA_RECON"}
    # UAV positions carried over from the previous terminal
    for aid, pos in uav_end.items():
        assert planned_session.state.agents[aid].position == pos

    while planned_session.phase is not SessionPhase.EXECUTED:
        advance_online_session(planned_session, mode="mock")
    assert planned_session.execution.termination is Termination.COMPLETED
    event_types = [e.event_type for e in planned_session.event_log]
    assert event_types.count("EXECUTION") == 2
    assert event_types[event_types.index("EXECUTION") + 1] == "TURN"


def test_new_mission_mid_run_abandons_the_paused_mission_and_opens_a_fresh_episode(
    planned_session,
):
    from llm.schemas import LLMTask, Step1Output, Step2Output

    advance_online_session(planned_session, mode="mock")
    advance_online_session(planned_session, mode="mock")
    assert planned_session.phase is SessionPhase.EXECUTION_PAUSED
    uav_mid = {
        aid: agent.position
        for aid, agent in planned_session.runtime.agents.items()
        if agent.platform_kind.name == "UAV"
    }
    executions_before = [
        e.event_type for e in planned_session.event_log
    ].count("EXECUTION")

    zones = sorted(planned_session.scene.zones)
    backend = MockBackend(
        [
            wire_intent("NEW_MISSION"),
            Step1Output(tasks=[LLMTask(task_type="AREA_RECON", target=z) for z in zones]),
            Step2Output(edges=[]),
        ]
    )
    result = handle_turn(planned_session, "이거 그만하고 전체 정찰 다시 해줘", backend)

    assert result.outcome is TurnOutcome.COMMITTED
    assert planned_session.phase is SessionPhase.PLANNING
    assert planned_session.runtime is None
    assert {t.task_type.value for t in planned_session.state.graph.tasks} == {"AREA_RECON"}
    for aid, pos in uav_mid.items():
        assert planned_session.state.agents[aid].position == pos
    # the abandoned mission never produced an EXECUTION audit
    assert [e.event_type for e in planned_session.event_log].count(
        "EXECUTION"
    ) == executions_before

    while planned_session.phase is not SessionPhase.EXECUTED:
        advance_online_session(planned_session, mode="mock")
    assert planned_session.execution.termination is Termination.COMPLETED


def test_new_mission_is_still_refused_from_a_failed_run(planned_session, monkeypatch):
    from execution.executor import SimExecutor

    original = SimExecutor.advance_to_next_completion

    def boom(self, *a, **k):
        raise RuntimeError("exec exploded")

    monkeypatch.setattr(SimExecutor, "advance_to_next_completion", boom)
    advance_online_session(planned_session, mode="mock")
    assert planned_session.phase is SessionPhase.EXECUTION_FAILED
    monkeypatch.setattr(SimExecutor, "advance_to_next_completion", original)

    result = handle_turn(
        planned_session, "전체 정찰 다시", MockBackend([wire_intent("NEW_MISSION")])
    )
    assert result.outcome is TurnOutcome.UNSUPPORTED


def test_scene_only_terminal_report_can_be_followed_by_canonical_update(
    planned_session,
):
    while planned_session.phase is not SessionPhase.EXECUTED:
        advance_online_session(planned_session, mode="mock")

    terminal_runtime = planned_session.runtime
    terminal_execution = planned_session.execution
    report = _turn(
        planned_session,
        "Warehouse에 불이 났어",
        "REPORT_INCIDENT",
        zone_ref="Warehouse",
    )

    assert report.outcome is TurnOutcome.COMMITTED
    assert planned_session.phase is SessionPhase.EXECUTED
    assert planned_session.execution is terminal_execution
    assert planned_session.runtime is terminal_runtime
    assert planned_session.runtime.scene is planned_session.scene

    update = _turn(
        planned_session,
        "거기 지상 진압까지 대응해줘",
        "UPDATE_MISSION",
        target_phrase="거기",
        up_to_step="GROUND_SUPPRESSION",
    )

    assert update.outcome is TurnOutcome.COMMITTED
    assert planned_session.phase is SessionPhase.EXECUTION_PAUSED
    assert planned_session.execution is None
    assert len(
        [task for task in planned_session.state.graph.tasks if task.target == "FIRE_SITE_3"]
    ) == 2


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
    # D-061: a new incident's GI (UGV) shares no bidder with the recon tasks (UAV),
    # so selective release for a brand-new incident is empty.
    assert update.audit.online_reallocation.selectively_released_tasks == []
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
    assert len(planned_session.execution.completed) == 10
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
                        (TaskType.GROUND_INSPECTION, "FIRE_SITE_1"),
                        (TaskType.GROUND_INSPECTION, "FIRE_SITE_2"),
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


# -- online retry after a failed advance (§19.1, D-041) -------------------


@contextmanager
def _exploding(monkeypatch):
    """Scope the executor patch to a block.

    ``monkeypatch.undo()`` would revert *every* patch on that instance, not
    just this one — including a fixture's ``setenv`` — so the failure injection
    is always confined to a context instead.
    """

    def boom(self, *args, **kwargs):
        raise RuntimeError("sim exploded")

    with monkeypatch.context() as patch:
        patch.setattr(SimExecutor, "advance_to_next_completion", boom)
        yield


@contextmanager
def _terminating(monkeypatch, termination):
    def ended(self, *args, **kwargs):
        return CompletionAdvance(self.checkpoint(), (), self._result(termination))

    with monkeypatch.context() as patch:
        patch.setattr(SimExecutor, "advance_to_next_completion", ended)
        yield


def test_a_failed_advance_keeps_the_runtime_and_stays_resumable(
    planned_session, monkeypatch
):
    advance_online_session(planned_session, mode="mock")
    good = _runtime_signature(planned_session.runtime)

    with _exploding(monkeypatch):
        audit = advance_online_session(planned_session, mode="mock")

    # §19.1 table: EXECUTION_FAILED + no execution + a runtime == resumable.
    assert planned_session.phase is SessionPhase.EXECUTION_FAILED
    assert planned_session.execution is None
    assert planned_session.runtime is not None
    assert audit.execution_termination == "ERROR"
    assert audit.error_type == "RuntimeError"
    # the preserved checkpoint is exactly the last good one — nothing rewound
    assert _runtime_signature(planned_session.runtime) == good


def test_online_execution_resumes_from_the_preserved_checkpoint(
    planned_session, monkeypatch
):
    advance_online_session(planned_session, mode="mock")
    paused_at = planned_session.runtime.now
    with _exploding(monkeypatch):
        advance_online_session(planned_session, mode="mock")

    audit = advance_online_session(planned_session, mode="mock")

    assert isinstance(audit, CheckpointAudit)
    assert planned_session.phase is SessionPhase.EXECUTION_PAUSED
    # a retry continues the same run rather than restarting it
    assert planned_session.runtime.now > paused_at


def test_a_resumed_run_still_finishes_on_the_golden_makespan(
    planned_session, monkeypatch
):
    advance_online_session(planned_session, mode="mock")
    with _exploding(monkeypatch):
        advance_online_session(planned_session, mode="mock")

    advance_online_session(planned_session, mode="mock")  # the retry itself
    for _ in range(60):
        if planned_session.phase is not SessionPhase.EXECUTION_PAUSED:
            break
        advance_online_session(planned_session, mode="mock")

    assert planned_session.phase is SessionPhase.EXECUTED
    result = planned_session.execution
    assert result.termination.value == "COMPLETED"
    assert result.makespan == pytest.approx(149.919688, abs=1e-6)  # P4 golden (D-060+D-061)
    assert not result.capability_violations and not result.precedence_violations


def test_a_one_shot_failure_without_a_runtime_is_not_an_online_retry(planned_session):
    # §19.1 table row 2: EXECUTION_FAILED with no runtime belongs to the
    # one-shot path (§18.1), so the online action must refuse it.
    planned_session.phase = SessionPhase.EXECUTION_FAILED
    assert planned_session.runtime is None

    with pytest.raises(ValueError, match="preserved runtime"):
        advance_online_session(planned_session, mode="mock")


def test_a_completed_online_run_cannot_be_advanced_again(planned_session):
    for _ in range(60):
        if planned_session.phase is not SessionPhase.PLANNING and (
            planned_session.phase is not SessionPhase.EXECUTION_PAUSED
        ):
            break
        advance_online_session(planned_session, mode="mock")

    assert planned_session.phase is SessionPhase.EXECUTED
    with pytest.raises(ValueError, match="before completion"):
        advance_online_session(planned_session, mode="mock")


def test_a_terminal_deadlock_keeps_its_runtime_but_is_not_resumable(
    planned_session, monkeypatch
):
    """§19.1 table / D-042: an ExecutionResult means the run ended, not crashed."""
    advance_online_session(planned_session, mode="mock")

    with _terminating(monkeypatch, Termination.DEADLOCK):
        audit = advance_online_session(planned_session, mode="mock")

    assert isinstance(audit, ExecutionAudit)
    assert audit.execution_termination == "DEADLOCK"
    assert planned_session.phase is SessionPhase.EXECUTION_FAILED
    assert planned_session.execution is not None       # a result, not an exception
    assert planned_session.runtime is not None         # the runtime is still there

    # Resuming would repeat the same ending AND erase the recorded terminal
    # state by flipping the phase back to EXECUTION_PAUSED.
    with pytest.raises(ValueError, match="DEADLOCK"):
        advance_online_session(planned_session, mode="mock")

    assert planned_session.phase is SessionPhase.EXECUTION_FAILED
    assert planned_session.execution.termination is Termination.DEADLOCK
    assert [event.event_type for event in planned_session.event_log] == [
        "EXECUTION_CHECKPOINT",
        "EXECUTION",
    ]


def test_a_terminal_deadlock_cannot_open_a_follow_on_incident_episode(
    planned_session, monkeypatch
):
    advance_online_session(planned_session, mode="mock")
    with _terminating(monkeypatch, Termination.DEADLOCK):
        advance_online_session(planned_session, mode="mock")

    scene_before = planned_session.scene
    result = _turn(
        planned_session,
        "A 구역에 새 화재가 발생했어. 지상 진압까지 대응해줘",
        "REPORT_INCIDENT",
        zone_ref="A 구역",
        response_up_to="GROUND_SUPPRESSION",
    )

    assert result.outcome is TurnOutcome.UNSUPPORTED
    assert planned_session.phase is SessionPhase.EXECUTION_FAILED
    assert planned_session.execution.termination is Termination.DEADLOCK
    assert planned_session.scene is scene_before


def test_a_terminal_step_limit_is_also_not_resumable(planned_session, monkeypatch):
    advance_online_session(planned_session, mode="mock")

    with _terminating(monkeypatch, Termination.STEP_LIMIT):
        advance_online_session(planned_session, mode="mock")

    with pytest.raises(ValueError, match="STEP_LIMIT"):
        advance_online_session(planned_session, mode="mock")
