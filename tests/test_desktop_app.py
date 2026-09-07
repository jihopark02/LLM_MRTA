"""P11 two-window native client gates (§21)."""

# ruff: noqa: E402 -- the offscreen platform must be selected before Qt imports.

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from demo.mock_script import MOCK_COMMANDS, SENSOR_MOCK_COMMANDS
from desktop.app import build_windows
from desktop.controller import DesktopController
from execution.executor import SimExecutor


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def windows(qt_app, tmp_path):
    controller = DesktopController(runtime_root=tmp_path, frame_count=4)
    operator, simulator = build_windows(controller, playback_seconds=0.01)
    operator.show()
    simulator.show()
    qt_app.processEvents()
    yield controller, operator, simulator
    operator.close()
    qt_app.processEvents()


def _drain_until(app, condition, timeout=3.0):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.002)
    assert condition()


def _submit(operator, text):
    operator.command_input.setText(text)
    operator.submit_command()


def test_two_top_level_windows_share_one_controller_session(windows):
    controller, operator, simulator = windows
    assert operator.controller is controller
    assert operator.controller.session is controller.session
    assert operator.isWindow()
    assert simulator.isWindow()
    assert operator.windowTitle() != simulator.windowTitle()


def test_a_mock_mission_updates_the_compact_console_and_simulator(windows):
    controller, operator, simulator = windows
    _submit(operator, MOCK_COMMANDS[0])

    assert len(controller.session.state.graph.tasks) == 12
    assert operator.task_card.value.text() == "12"
    assert "COMMITTED" in operator.latest.text()
    assert simulator.canvas.spec.mode == "plan"
    assert "MOCK" in operator.mode_banner.text()


def test_checkpoint_playback_locks_input_then_reopens_it(windows, qt_app):
    controller, operator, simulator = windows
    _submit(operator, MOCK_COMMANDS[0])

    operator.play_checkpoint()
    assert operator._busy
    assert not operator.command_input.isEnabled()
    assert simulator.is_playing
    _drain_until(qt_app, lambda: not operator._busy)

    assert controller.session.phase.value == "EXECUTION_PAUSED"
    assert operator.command_input.isEnabled()
    assert "후속 명령 입력 가능" in operator.status.text()


def test_ambiguous_referent_is_resolved_by_a_native_candidate_button(windows):
    controller, operator, _ = windows
    _submit(operator, MOCK_COMMANDS[0])
    _submit(operator, MOCK_COMMANDS[1])

    assert controller.session.pending_clarification is not None
    buttons = [
        operator.candidate_buttons.itemAt(index).widget()
        for index in range(operator.candidate_buttons.count())
    ]
    selected = next(button for button in buttons if button.text() == "FIRE_SITE_1")
    selected.click()

    assert controller.session.pending_clarification is None
    assert controller.session.turn_log[-1].selected_entity_id == "FIRE_SITE_1"


def test_continuous_mode_runs_checkpoint_segments_to_terminal(windows, qt_app):
    controller, operator, simulator = windows
    _submit(operator, MOCK_COMMANDS[0])
    turns = controller.session.turn_count

    operator.play_continuous()
    assert operator._continuous
    assert not operator.command_input.isEnabled()
    _drain_until(qt_app, lambda: not operator._busy, timeout=6.0)

    assert controller.session.phase.value == "EXECUTED"
    assert controller.session.execution.termination.value == "COMPLETED"
    assert controller.session.turn_count == turns
    assert not operator._continuous
    assert not simulator.is_playing
    assert not operator.checkpoint_button.isEnabled()
    assert controller.session.event_log[-1].event_type == "EXECUTION"


def test_online_update_changes_the_next_native_playback(windows, qt_app):
    controller, operator, simulator = windows
    _submit(operator, MOCK_COMMANDS[0])
    operator.play_checkpoint()
    _drain_until(qt_app, lambda: not operator._busy)
    _submit(operator, MOCK_COMMANDS[1])
    operator.choose_candidate("FIRE_SITE_1")
    _submit(operator, MOCK_COMMANDS[2])
    _submit(operator, MOCK_COMMANDS[3])
    added = {
        task.task_id
        for task in controller.session.state.graph.tasks
        if task.target == "FIRE_SITE_3"
    }

    operator.play_checkpoint()

    shown = {
        leg.task_id
        for frame in simulator._frames
        for leg in frame.map_spec.legs
    }
    ready_added = {task_id for task_id in added if task_id.startswith("THERMAL_RECON")}
    assert ready_added and ready_added <= shown
    assert not operator.command_input.isEnabled()
    _drain_until(qt_app, lambda: not operator._busy)
    assert controller.session.phase.value == "EXECUTION_PAUSED"
    assert operator.command_input.isEnabled()


def test_continuous_mode_stops_on_an_execution_error_without_retry(
    windows, qt_app, monkeypatch
):
    controller, operator, _ = windows
    _submit(operator, MOCK_COMMANDS[0])
    original = SimExecutor.advance_to_next_completion
    calls = 0

    def fail_second(executor, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("native continuous exploded")
        return original(executor, *args, **kwargs)

    monkeypatch.setattr(SimExecutor, "advance_to_next_completion", fail_second)
    operator.play_continuous()
    _drain_until(qt_app, lambda: not operator._busy)

    assert calls == 2
    assert controller.session.phase.value == "EXECUTION_FAILED"
    assert controller.session.runtime is not None
    assert controller.session.execution is None
    assert not operator._continuous
    assert controller.session.event_log[-1].error_type == "RuntimeError"
    assert operator.checkpoint_button.isEnabled()  # explicit retry remains available


def test_sensor_scenario_is_explicit_and_refreshes_after_detection(qt_app, tmp_path):
    controller = DesktopController(
        runtime_root=tmp_path,
        frame_count=4,
        scenario_id="sensor-detection",
    )
    operator, simulator = build_windows(controller, playback_seconds=0.01)
    operator.show()
    simulator.show()
    qt_app.processEvents()
    try:
        assert operator.scenario_combo.currentData() == "sensor-detection"
        assert "simulated-fire-zone-b-v1" in operator.scenario_help.text()
        _submit(operator, SENSOR_MOCK_COMMANDS[0])
        assert "GROUND_SUPPRESSION" in operator.scenario_help.text()
        assert operator.task_card.value.text() == "4"

        operator.play_checkpoint()
        _drain_until(qt_app, lambda: not operator._busy)
        operator.play_checkpoint()
        _drain_until(qt_app, lambda: not operator._busy)

        assert operator.task_card.value.text() == "8"
        assert "SENSOR_SIMULATED" in operator.latest.text()
        assert "FIRE_SITE_1" in {
            point.entity_id for point in simulator.canvas.spec.incidents
        }
    finally:
        operator.close()
        qt_app.processEvents()
