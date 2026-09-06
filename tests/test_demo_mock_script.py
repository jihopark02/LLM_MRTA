"""The offline UI fallback is finite, labelled and follows its published order."""

from demo.mock_script import MOCK_COMMANDS, make_mock_backend
from interaction.orchestrator import (
    TurnOutcome,
    handle_turn,
    select_clarification_candidate,
)
from interaction.session import MissionSession
from scenarios.fixture import load_reference_fixture


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
