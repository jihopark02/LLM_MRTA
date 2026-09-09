"""P11 two-window native client gates (§21)."""

# ruff: noqa: E402 -- the offscreen platform must be selected before Qt imports.

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from demo.mock_script import MOCK_COMMANDS, OPERATOR_MOCK_COMMANDS, SENSOR_MOCK_COMMANDS
from desktop.app import build_windows
from desktop.controller import OPERATOR_LIVE_EXAMPLES, DesktopController
from execution.executor import SimExecutor
from interaction.session import SessionPhase


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def windows(qt_app, tmp_path):
    controller = DesktopController(
        runtime_root=tmp_path, frame_count=4, scenario_id="reference"
    )
    operator, simulator = build_windows(
        controller, playback_seconds=0.01, auto_run=False, sim_rate=1500.0
    )
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

    assert len(controller.session.state.graph.tasks) == 8
    assert operator.task_card.value.text() == "8"
    assert "COMMITTED" in operator.latest.text()
    assert simulator.canvas.spec.mode == "plan"
    assert "MOCK" in operator.mode_banner.text()


def test_cached_help_is_never_labelled_live_and_shows_the_exact_replay(windows):
    controller, operator, _ = windows
    controller.new_session("operator-report")
    controller.set_mode("cached")
    operator.refresh()

    assert "CACHED" in operator.mode_banner.text()
    assert "CACHED exact replay" in operator.scenario_help.text()
    assert "LIVE" not in operator.scenario_help.text()
    assert OPERATOR_LIVE_EXAMPLES[0] in operator.scenario_help.text()
    assert OPERATOR_LIVE_EXAMPLES[1] in operator.scenario_help.text()


def test_checkpoint_playback_accepts_one_queued_input_then_reopens_it(windows, qt_app):
    controller, operator, simulator = windows
    _submit(operator, MOCK_COMMANDS[0])

    operator.play_checkpoint()
    assert operator._busy
    assert operator.command_input.isEnabled()
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
    assert operator.command_input.isEnabled()
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
    ready_added = {task_id for task_id in added if task_id.startswith("GROUND_INSPECTION")}
    assert ready_added and ready_added <= shown
    assert operator.command_input.isEnabled()
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
    operator, simulator = build_windows(
        controller, playback_seconds=0.01, auto_run=False, sim_rate=1500.0
    )
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

        assert operator.task_card.value.text() == "6"
        assert "SENSOR_SIMULATED" in operator.latest.text()
        assert "FIRE_SITE_1" in {
            point.entity_id for point in simulator.canvas.spec.incidents
        }
    finally:
        operator.close()
        qt_app.processEvents()


def test_initial_commit_autoplays_and_mid_segment_report_is_applied_once(
    qt_app, tmp_path, monkeypatch
):
    controller = DesktopController(
        runtime_root=tmp_path,
        frame_count=8,
        scenario_id="operator-report",
    )
    operator, simulator = build_windows(
        controller, playback_seconds=0.08, auto_run=True, sim_rate=1500.0
    )
    operator.show()
    simulator.show()
    qt_app.processEvents()
    rendered_task_sets = []
    original_render = simulator.render_frame

    def capture_frame(frame):
        rendered_task_sets.append({leg.task_id for leg in frame.map_spec.legs})
        original_render(frame)

    monkeypatch.setattr(simulator, "render_frame", capture_frame)
    try:
        _submit(operator, OPERATOR_MOCK_COMMANDS[0])
        _drain_until(qt_app, lambda: operator._continuous)
        backend = controller.backends["mock"]
        calls_before = len(backend.calls)
        turns_before = controller.session.turn_count

        assert operator.command_input.isEnabled()
        _submit(operator, OPERATOR_MOCK_COMMANDS[1])

        assert controller.queued_command == OPERATOR_MOCK_COMMANDS[1]
        assert len(backend.calls) == calls_before
        assert controller.session.turn_count == turns_before
        assert operator.command_input.isEnabled()  # more commands may be queued
        assert "QUEUED" in operator.status.text()

        _drain_until(qt_app, lambda: not operator._busy, timeout=6.0)

        assert controller.queued_command is None
        assert controller.session.turn_count == turns_before + 1
        assert len(backend.calls) == calls_before + 1
        assert len(controller.session.state.graph) == 6
        assert controller.session.phase.value == "EXECUTED"
        assert controller.session.execution.termination.value == "COMPLETED"
        assert any("[QUEUED #" in message.text for message in controller.chat)
        assert any(
            "GROUND_INSPECTION__FIRE_SITE_1" in task_ids
            for task_ids in rendered_task_sets
        )
    finally:
        operator.close()
        qt_app.processEvents()


def test_completed_patrol_report_opens_and_autoplays_a_follow_on_episode(
    qt_app, tmp_path
):
    controller = DesktopController(
        runtime_root=tmp_path,
        frame_count=4,
        scenario_id="operator-report",
    )
    operator, simulator = build_windows(
        controller, playback_seconds=0.01, auto_run=True, sim_rate=1500.0
    )
    operator.show()
    simulator.show()
    qt_app.processEvents()
    try:
        _submit(operator, OPERATOR_MOCK_COMMANDS[0])
        _drain_until(qt_app, lambda: operator._busy)
        _drain_until(qt_app, lambda: not operator._busy, timeout=6.0)
        assert controller.session.phase is SessionPhase.EXECUTED
        assert len(controller.session.state.graph) == 4

        _submit(operator, OPERATOR_MOCK_COMMANDS[1])
        _drain_until(qt_app, lambda: operator._busy)
        _drain_until(qt_app, lambda: not operator._busy, timeout=6.0)

        assert controller.session.phase is SessionPhase.EXECUTED
        assert controller.session.execution.termination.value == "COMPLETED"
        assert len(controller.session.state.graph) == 6
        assert [event.event_type for event in controller.session.event_log].count(
            "EXECUTION"
        ) == 2
    finally:
        operator.close()
        qt_app.processEvents()


def test_queued_clarification_stops_autoplay_at_the_safe_checkpoint(
    qt_app, tmp_path
):
    controller = DesktopController(
        runtime_root=tmp_path,
        frame_count=8,
        scenario_id="reference",
    )
    operator, simulator = build_windows(
        controller, playback_seconds=0.08, auto_run=True, sim_rate=1500.0
    )
    operator.show()
    simulator.show()
    qt_app.processEvents()
    try:
        _submit(operator, MOCK_COMMANDS[0])
        _drain_until(qt_app, lambda: operator._continuous)
        _submit(operator, MOCK_COMMANDS[1])

        _drain_until(qt_app, lambda: not operator._busy)

        assert controller.session.pending_clarification is not None
        assert controller.session.phase.value == "EXECUTION_PAUSED"
        assert not operator._continuous
        assert "CLARIFICATION" in operator.status.text()
        assert operator.candidate_frame.isVisible()
    finally:
        operator.close()
        qt_app.processEvents()


def test_sensor_fire_gate_lets_recon_finish_then_resumes_on_approve(qt_app, tmp_path):
    import yaml

    from scenarios.latent import SimulatedFireField, load_latent_fire_field

    controller = DesktopController(
        runtime_root=tmp_path, frame_count=4, scenario_id="operator-report"
    )
    operator, simulator = build_windows(
        controller, playback_seconds=0.01, auto_run=True, sim_rate=1500.0
    )
    operator.show()
    simulator.show()
    qt_app.processEvents()
    try:
        _submit(operator, OPERATOR_MOCK_COMMANDS[0])
        _drain_until(qt_app, lambda: operator._continuous)
        spec = tmp_path / "field.yaml"
        spec.write_text(
            yaml.safe_dump(
                {"field_id": "g", "seed": 1, "count": 1, "candidate_zones": ["ZONE_A"]}
            )
        )
        controller.observation_source = SimulatedFireField(
            load_latent_fire_field(spec, controller.session.scene)
        )

        # D-067: nobody answers, so the recon runs to completion and only then
        # does the clock hold for the operator — it never froze mid-patrol.
        _drain_until(qt_app, lambda: not operator._busy, timeout=6.0)

        assert controller.pending_fire_approval is not None
        assert operator.approval_frame.isVisible()
        assert not operator._continuous
        assert "FIRE_SITE_1" not in controller.session.scene.incidents

        buttons = [
            operator.approval_buttons.itemAt(i).widget()
            for i in range(operator.approval_buttons.count())
        ]
        approve = next(b for b in buttons if "진압까지" in b.text())
        approve.click()

        # recon was already done, so the decision opens a follow-on episode now
        assert controller.pending_fire_approval is None
        assert "FIRE_SITE_1" in controller.session.scene.incidents
        _drain_until(
            qt_app,
            lambda: controller.session.phase.value == "EXECUTED",
            timeout=8.0,
        )
        assert controller.session.execution.termination.value == "COMPLETED"
    finally:
        operator.close()
        qt_app.processEvents()
