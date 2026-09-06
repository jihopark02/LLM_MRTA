"""P8.3 deterministic run action and chronological execution audit (§18.9)."""

import json
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

from allocation.allocate import allocate
from execution.executor import SimExecutor as RealSimExecutor
from execution.executor import Termination
from interaction.audit_io import session_audit_payload
from interaction.execute import execute_session
from interaction.orchestrator import TurnOutcome, handle_turn
from interaction.schemas import IntentEnvelope
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
from validator.hashing import pre_state_hash, scene_hash

SCENARIOS = Path(__file__).parents[1] / "scenarios"


def _intent(kind: str, **slots) -> IntentEnvelope:
    return IntentEnvelope.model_validate({"intent": {"kind": kind, **slots}})


@pytest.fixture
def planned_session():
    scene = load_scene(SCENARIOS / "industrial_park.yaml")
    graph = load_reference_fixture().graph
    state = fresh_session_state(graph, scene)
    return MissionSession(
        session_id="RUN",
        scene=scene,
        state=state,
        plan=allocate(state, scene),
    )


def test_completed_execution_is_stored_and_audited_without_consuming_a_turn(planned_session):
    session = planned_session
    state, plan, scene = session.state, session.plan, session.scene
    state_fingerprint = pre_state_hash(state)
    scene_fingerprint = scene_hash(scene)
    plan_snapshot = deepcopy(plan)
    turn_count = session.turn_count

    audit = execute_session(session, mode="mock")

    assert audit.execution_termination == "COMPLETED"
    assert session.execution is not None
    assert session.phase is SessionPhase.EXECUTED
    assert session.turn_count == turn_count
    assert session.event_log == (audit,)
    assert session.state is state
    assert session.plan is plan
    assert session.scene is scene
    assert pre_state_hash(session.state) == state_fingerprint
    assert scene_hash(session.scene) == scene_fingerprint
    assert session.plan == plan_snapshot
    assert audit.plan_assignments == plan.assignments
    assert audit.execution_assignments == session.execution.assignments
    assert audit.capability_violations == [] and audit.precedence_violations == []
    assert datetime.fromisoformat(audit.started_at) <= datetime.fromisoformat(audit.finished_at)


def test_event_stream_preserves_t1_t2_execution_t3_order(planned_session):
    session = planned_session
    handle_turn(session, "상태 1", MockBackend([_intent("QUERY_STATUS")]))
    handle_turn(session, "상태 2", MockBackend([_intent("QUERY_STATUS")]))
    execute_session(session, mode="mock")
    last = handle_turn(session, "실행 결과", MockBackend([_intent("QUERY_STATUS")]))

    payload = session_audit_payload(session)
    assert [event["event_type"] for event in payload["events"]] == [
        "TURN",
        "TURN",
        "EXECUTION",
        "TURN",
    ]
    assert [event.get("turn_id") for event in payload["events"]] == ["t1", "t2", None, "t3"]
    assert [event["event_seq"] for event in payload["events"]] == [0, 1, 2, 3]
    assert session.turn_count == 3
    assert last.outcome is TurnOutcome.ANSWERED
    assert "실행 결과 COMPLETED" in last.message
    json.dumps(payload)


def test_non_completed_result_moves_to_execution_failed_and_is_kept(
    planned_session, monkeypatch
):
    from interaction import execute

    result = RealSimExecutor(planned_session.state, planned_session.scene).run()
    result = replace(result, termination=Termination.STEP_LIMIT, unfinished_tasks=["T"])

    class StepLimited:
        def __init__(self, *args):
            pass

        def run(self):
            return result

    monkeypatch.setattr(execute, "SimExecutor", StepLimited)
    audit = execute_session(planned_session, mode="cached")

    assert audit.execution_termination == "STEP_LIMIT"
    assert audit.mode == "cached"
    assert planned_session.execution is result
    assert planned_session.phase is SessionPhase.EXECUTION_FAILED


def test_executor_exception_is_isolated_and_audited(planned_session, monkeypatch):
    from interaction import execute

    class Boom:
        def __init__(self, *args):
            pass

        def run(self):
            raise RuntimeError("executor boom")

    monkeypatch.setattr(execute, "SimExecutor", Boom)
    audit = execute_session(planned_session, mode="live")

    assert audit.execution_termination == "ERROR"
    assert audit.error_type == "RuntimeError"
    assert audit.error_detail == "executor boom"
    assert planned_session.execution is None
    assert planned_session.phase is SessionPhase.EXECUTION_FAILED
    assert planned_session.event_log[-1] is audit


def test_failed_execution_can_retry_the_same_graph(planned_session, monkeypatch):
    from interaction import execute

    class Boom:
        def __init__(self, *args):
            pass

        def run(self):
            raise RuntimeError("first attempt")

    graph_before = planned_session.state.graph
    monkeypatch.setattr(execute, "SimExecutor", Boom)
    execute_session(planned_session, mode="live")
    monkeypatch.setattr(execute, "SimExecutor", RealSimExecutor)

    retry = execute_session(planned_session, mode="mock")

    assert retry.execution_termination == "COMPLETED"
    assert planned_session.phase is SessionPhase.EXECUTED
    assert planned_session.state.graph is graph_before
    assert [event.execution_termination for event in planned_session.event_log] == [
        "ERROR",
        "COMPLETED",
    ]


@pytest.mark.parametrize("bad_mode", [None, "LIVE", "", [], True])
def test_execution_requires_exact_mode_without_mutating_the_session(planned_session, bad_mode):
    with pytest.raises(ValueError, match="mode"):
        execute_session(planned_session, mode=bad_mode)
    assert planned_session.phase is SessionPhase.PLANNING
    assert planned_session.event_log == ()


def test_execution_preconditions_fail_before_an_event(planned_session):
    scene = planned_session.scene
    no_mission = MissionSession("EMPTY", scene)
    with pytest.raises(ValueError, match="mission and plan"):
        execute_session(no_mission, mode="mock")

    no_plan = MissionSession("NO_PLAN", scene, state=planned_session.state)
    with pytest.raises(ValueError, match="mission and plan"):
        execute_session(no_plan, mode="mock")

    planned_session.pending_clarification = PendingClarification(
        source_turn_id="t1",
        intent_kind="UPDATE_MISSION",
        extracted_slots={"target_phrase": "그 화재", "up_to_step": "GROUND_SUPPRESSION"},
        unresolved_slot="target_phrase",
        entity_kind=ReferentKind.INCIDENT,
        candidates=("FIRE_SITE_1", "FIRE_SITE_2"),
        original_utterance="그 화재 진압까지",
    )
    with pytest.raises(ValueError, match="pending clarification"):
        execute_session(planned_session, mode="mock")
    assert planned_session.event_log == ()


def test_completed_session_cannot_run_twice(planned_session):
    execute_session(planned_session, mode="mock")
    before = planned_session.event_log
    with pytest.raises(ValueError, match="already completed"):
        execute_session(planned_session, mode="mock")
    assert planned_session.event_log == before
