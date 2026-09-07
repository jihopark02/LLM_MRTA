"""The offline UI fallback is finite, labelled and exact, never a fake LLM."""

from demo.mock_script import (
    MOCK_COMMANDS,
    OPERATOR_MOCK_COMMANDS,
    OPERATOR_SCRIPT,
    SENSOR_MOCK_COMMANDS,
    SENSOR_SCRIPT,
    make_mock_backend,
)
from interaction.orchestrator import (
    TurnOutcome,
    handle_turn,
    select_clarification_candidate,
)
from interaction.session import MissionSession
from scenarios.fixture import load_reference_fixture
from scenarios.scene import load_scene


def test_mock_script_runs_the_documented_natural_language_sequence():
    scene = load_reference_fixture().scene
    session = MissionSession("MOCK-DEMO", scene)
    backend = make_mock_backend()

    outcomes = []
    for index, command in enumerate(MOCK_COMMANDS):
        outcomes.append(handle_turn(session, command, backend).outcome)
        if index == 1:
            selected = select_clarification_candidate(
                session, "FIRE_SITE_1", mode="mock"
            )
            assert selected.outcome is TurnOutcome.ANSWERED

    assert outcomes == [
        TurnOutcome.COMMITTED,
        TurnOutcome.CLARIFICATION,
        TurnOutcome.COMMITTED,
        TurnOutcome.COMMITTED,
        TurnOutcome.ANSWERED,
        TurnOutcome.UNSUPPORTED,
    ]


def test_unknown_mock_text_is_rejected_without_consuming_the_next_item():
    scene = load_reference_fixture().scene
    session = MissionSession("MOCK-EXACT", scene)
    backend = make_mock_backend()

    rejected = handle_turn(session, "uav 하나로 순찰해줘", backend)
    assert rejected.outcome is TurnOutcome.TURN_ERROR
    assert "UnsupportedMockCommand" in rejected.error
    assert backend.remaining > 0
    assert backend.calls == []
    assert len(backend.rejected_calls) == 1

    accepted = handle_turn(session, MOCK_COMMANDS[0], backend)
    assert accepted.outcome is TurnOutcome.COMMITTED
    assert len(session.state.graph) == 12


def test_sensor_script_extracts_patrol_graph_and_future_response_policy():
    scene = load_scene("scenarios/patrol_park.yaml")
    session = MissionSession("MOCK-SENSOR", scene)
    backend = make_mock_backend(SENSOR_SCRIPT)

    result = handle_turn(session, SENSOR_MOCK_COMMANDS[0], backend)

    assert result.outcome is TurnOutcome.COMMITTED
    assert len(session.state.graph) == 4
    assert {task.task_type.value for task in session.state.graph.tasks} == {"AREA_RECON"}
    assert session.directive.incident_response_up_to.value == "GROUND_SUPPRESSION"


def test_operator_script_report_is_one_turn_response_not_a_second_update():
    scene = load_scene("scenarios/patrol_park.yaml")
    session = MissionSession("MOCK-OPERATOR", scene)
    backend = make_mock_backend(OPERATOR_SCRIPT)
    assert handle_turn(session, OPERATOR_MOCK_COMMANDS[0], backend).outcome is TurnOutcome.COMMITTED

    report = handle_turn(session, OPERATOR_MOCK_COMMANDS[1], backend)

    assert report.outcome is TurnOutcome.COMMITTED
    assert report.audit.incident_action.response_up_to == "GROUND_SUPPRESSION"
    assert len([task for task in session.state.graph.tasks if task.target == "FIRE_SITE_1"]) == 4
