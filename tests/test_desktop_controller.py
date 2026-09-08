"""P11 Qt-independent presentation controller gates (§21)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from demo.mock_script import (
    MOCK_COMMANDS,
    OPERATOR_MOCK_COMMANDS,
    SENSOR_MOCK_COMMANDS,
)
from desktop.controller import DesktopController
from interaction.audit import CheckpointAudit, IncidentObservationAudit


def _controller(tmp_path):
    return DesktopController(
        runtime_root=tmp_path, frame_count=4, scenario_id="reference"
    )


def test_native_default_is_the_sensor_detection_presentation(tmp_path):
    controller = DesktopController(runtime_root=tmp_path, frame_count=4)

    assert controller.scenario_id == "sensor-detection"
    assert controller.fixture_id == "simulated-fire-zone-b-v1"


def test_importing_the_desktop_package_does_not_import_qt():
    probe = "import sys,desktop;print(any(n.startswith('PySide6') for n in sys.modules))"
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=Path(__file__).parents[1],
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "False"


def test_module_entrypoint_explains_the_missing_optional_qt_dependency():
    probe = r'''
import importlib.abc
import runpy
import sys

class BlockQt(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "PySide6" or fullname.startswith("PySide6."):
            raise ModuleNotFoundError("blocked for test", name="PySide6")
        return None

sys.meta_path.insert(0, BlockQt())
try:
    runpy.run_module("desktop", run_name="__main__")
except SystemExit as exc:
    print(exc)
'''
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=Path(__file__).parents[1],
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        check=True,
    )
    assert "pip install -e '.[desktop]'" in result.stdout


def test_mock_mission_uses_the_existing_orchestrator_and_writes_audit(tmp_path):
    controller = _controller(tmp_path)
    session = controller.session

    result = controller.submit(MOCK_COMMANDS[0])

    assert controller.session is session
    assert result.outcome.value == "COMMITTED"
    assert len(session.state.graph.tasks) == 12
    assert len(session.state.graph.edges) == 6
    assert session.plan.allocation_success
    audit = controller.audit_directory / f"{session.session_id}.json"
    assert audit.is_file()
    assert '"mode": "mock"' in audit.read_text(encoding="utf-8")


def test_checkpoint_action_returns_the_frozen_p10_playback(tmp_path):
    controller = _controller(tmp_path)
    controller.submit(MOCK_COMMANDS[0])
    result = controller.advance_checkpoint()

    assert isinstance(result.audit, CheckpointAudit)
    assert result.playback_error is None
    assert result.playback is not None
    assert result.playback.start_time < result.playback.end_time
    assert len(result.playback.frames) == 4
    assert controller.session.phase.value == "EXECUTION_PAUSED"
    assert controller.current_map_spec().mode == "runtime"


def test_structured_candidate_and_online_update_enter_the_next_segment(tmp_path):
    controller = _controller(tmp_path)
    controller.submit(MOCK_COMMANDS[0])
    controller.advance_checkpoint()
    clarification = controller.submit(MOCK_COMMANDS[1])
    assert clarification.outcome.value == "CLARIFICATION"
    controller.select_candidate("FIRE_SITE_1")
    controller.submit(MOCK_COMMANDS[2])
    update = controller.submit(MOCK_COMMANDS[3])
    assert update.outcome.value == "COMMITTED"

    added = {
        task.task_id
        for task in controller.session.state.graph.tasks
        if task.target == "FIRE_SITE_3"
    }
    assert len(added) == 4
    presentation = controller.advance_checkpoint()
    shown = {
        leg.task_id
        for frame in presentation.playback.frames
        for leg in frame.map_spec.legs
    }
    ready_added = {task_id for task_id in added if task_id.startswith("THERMAL_RECON")}
    assert ready_added <= shown
    assert controller.current_map_spec().mode == "runtime"


def test_a_new_session_replaces_presentation_state_and_mock_backend(tmp_path):
    controller = _controller(tmp_path)
    controller.submit(MOCK_COMMANDS[0])
    old_session = controller.session
    old_backend = controller.backends["mock"]

    controller.new_session()

    assert controller.session is not old_session
    assert controller.chat == []
    assert controller.backends == {}
    controller.submit(MOCK_COMMANDS[0])
    assert controller.backends["mock"] is not old_backend


def test_queued_command_does_not_call_backend_until_safe_checkpoint(tmp_path):
    controller = DesktopController(
        runtime_root=tmp_path,
        frame_count=4,
        scenario_id="operator-report",
    )
    controller.submit(OPERATOR_MOCK_COMMANDS[0])
    backend = controller.backends["mock"]
    calls_before = len(backend.calls)
    turns_before = controller.session.turn_count

    controller.queue_command(OPERATOR_MOCK_COMMANDS[1])

    assert controller.queued_command == OPERATOR_MOCK_COMMANDS[1]
    assert len(backend.calls) == calls_before
    assert controller.session.turn_count == turns_before
    assert len(controller.session.state.graph) == 4
    with pytest.raises(ValueError, match="already queued"):
        controller.queue_command("두 번째 명령")

    controller.advance_checkpoint()
    result = controller.submit_queued()

    assert result.outcome.value == "COMMITTED"
    assert controller.queued_command is None
    assert len(backend.calls) == calls_before + 1
    assert controller.session.turn_count == turns_before + 1
    assert len(controller.session.state.graph) == 8


@pytest.mark.parametrize("mode", ["", "LIVE", "fake", None])
def test_mode_is_strict(mode, tmp_path):
    controller = _controller(tmp_path)
    with pytest.raises(ValueError, match="mode"):
        controller.set_mode(mode)


def test_execution_requires_a_committed_plan(tmp_path):
    controller = _controller(tmp_path)
    with pytest.raises(ValueError, match="mission and plan"):
        controller.advance_checkpoint()


def test_sensor_scenario_reveals_fixture_once_and_adds_response_in_one_event(tmp_path):
    controller = DesktopController(
        runtime_root=tmp_path,
        frame_count=4,
        scenario_id="sensor-detection",
    )
    result = controller.submit(SENSOR_MOCK_COMMANDS[0])
    assert result.outcome.value == "COMMITTED"
    assert len(controller.session.state.graph) == 4
    assert controller.fixture_id == "simulated-fire-zone-b-v1"
    assert controller.session.directive.incident_response_up_to.value == "GROUND_SUPPRESSION"

    observations = []
    for _ in range(4):
        presentation = controller.advance_checkpoint()
        if presentation.observation is not None:
            observations.append(presentation.observation)
            break

    assert len(observations) == 1
    observation = observations[0]
    assert isinstance(observation, IncidentObservationAudit)
    assert observation.outcome == "COMMITTED"
    assert observation.zone_id == "ZONE_B"
    assert observation.online_reallocation is not None
    assert len(controller.session.state.graph) == 8
    assert {task.target for task in controller.session.state.graph.tasks} >= {
        "FIRE_SITE_1"
    }
    assert [event.event_type for event in controller.session.event_log].count(
        "INCIDENT_OBSERVATION"
    ) == 1


def test_sensor_observation_precedes_a_queued_command_at_the_same_checkpoint(tmp_path):
    controller = DesktopController(
        runtime_root=tmp_path,
        frame_count=4,
        scenario_id="sensor-detection",
    )
    controller.submit(SENSOR_MOCK_COMMANDS[0])
    presentation = controller.advance_checkpoint()
    while presentation.observation is None:
        presentation = controller.advance_checkpoint()

    controller.queue_command(SENSOR_MOCK_COMMANDS[1])
    result = controller.submit_queued()

    assert result.outcome.value == "ANSWERED"
    event_types = [event.event_type for event in controller.session.event_log]
    assert event_types[-2:] == ["INCIDENT_OBSERVATION", "TURN"]

    controller.advance_checkpoint()
    assert [event.event_type for event in controller.session.event_log].count(
        "INCIDENT_OBSERVATION"
    ) == 1


def test_operator_scenario_changes_online_assignment_from_one_natural_turn(tmp_path):
    controller = DesktopController(
        runtime_root=tmp_path,
        frame_count=4,
        scenario_id="operator-report",
    )
    controller.submit(OPERATOR_MOCK_COMMANDS[0])
    controller.advance_checkpoint()
    runtime_before = controller.session.runtime

    result = controller.submit(OPERATOR_MOCK_COMMANDS[1])

    assert result.outcome.value == "COMMITTED"
    assert result.audit.incident_action.source == "OPERATOR"
    assert result.audit.incident_action.zone_id == "ZONE_A"
    assert result.audit.incident_action.response_up_to == "GROUND_SUPPRESSION"
    assert result.audit.online_reallocation is not None
    assert controller.session.runtime is not runtime_before
    assert len(controller.session.state.graph) == 8


def test_switching_scenario_replaces_scene_fixture_backend_and_session(tmp_path):
    controller = _controller(tmp_path)
    old_session = controller.session
    controller._backend()

    controller.new_session("sensor-detection")

    assert controller.session is not old_session
    assert controller.session.scene.scene_id == "patrol_park"
    assert controller.fixture_id == "simulated-fire-zone-b-v1"
    assert controller.backends == {}
    assert controller.mock_commands == SENSOR_MOCK_COMMANDS
