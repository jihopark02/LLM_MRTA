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
from desktop.controller import ContinuousRuntime, DesktopController
from interaction.audit import CheckpointAudit, IncidentObservationAudit


def _run_continuous(controller, *, step: float = 3.0, max_ticks: int = 400):
    """Drive a ContinuousRuntime to a terminal or halt, returning every tick."""
    runtime = ContinuousRuntime(controller)
    ticks = [runtime.start()]
    guard = 0
    while runtime.active and guard < max_ticks:
        ticks.append(runtime.advance_to(runtime.sim_time + step))
        guard += 1
    return runtime, ticks


def _controller(tmp_path):
    return DesktopController(
        runtime_root=tmp_path, frame_count=4, scenario_id="reference"
    )


def test_native_default_is_scenario_free_live_world(tmp_path):
    controller = DesktopController(runtime_root=tmp_path, frame_count=4)

    assert controller.scenario_id == "dynamic-world"
    assert controller.mode == "live"
    assert controller.fixture_id is None
    assert controller.session.scene.incidents == {}
    assert controller.session.state is None
    assert controller.mock_commands == ()


def test_dynamic_district_is_an_incident_empty_eight_zone_live_world(tmp_path):
    controller = DesktopController(
        runtime_root=tmp_path, frame_count=4, scenario_id="dynamic-district"
    )

    assert controller.mode == "live"
    assert controller.fixture_id is None
    assert controller.mock_commands == ()
    assert controller.session.scene.scene_id == "response_district_patrol"
    assert controller.session.scene.incidents == {}
    assert len(controller.session.scene.zones) == 8
    assert controller.session.state is None


def test_dynamic_world_never_falls_back_to_a_mock_mission(tmp_path):
    controller = DesktopController(runtime_root=tmp_path, frame_count=4)
    controller.set_mode("mock")

    with pytest.raises(ValueError, match="no mock script"):
        controller.submit("전체 구역을 정찰해줘")

    assert controller.session.state is None
    assert controller.chat == []
    assert controller.backends == {}


def test_dynamic_world_live_failure_is_audited_without_script_fallback(tmp_path):
    controller = DesktopController(runtime_root=tmp_path, frame_count=4)

    class Offline:
        mode = "live"

        def complete(self, *args, **kwargs):
            raise ConnectionError("network unavailable")

    controller.backends["live"] = Offline()
    result = controller.submit("UAV 한 대로 Warehouse를 정찰해줘")

    assert result.outcome.value == "TURN_ERROR"
    assert result.audit.mode == "live"
    assert result.audit.error_type == "ConnectionError"
    assert controller.session.state is None
    assert "mock" not in controller.backends


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
    assert len(session.state.graph.tasks) == 8
    assert len(session.state.graph.edges) == 2
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
    assert len(added) == 2
    presentation = controller.advance_checkpoint()
    shown = {
        leg.task_id
        for frame in presentation.playback.frames
        for leg in frame.map_spec.legs
    }
    ready_added = {task_id for task_id in added if task_id.startswith("GROUND_INSPECTION")}
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

    controller.advance_checkpoint()
    result = controller.submit_queued()

    assert result.outcome.value == "COMMITTED"
    assert controller.queued_command is None
    assert len(backend.calls) == calls_before + 1
    assert controller.session.turn_count == turns_before + 1
    assert len(controller.session.state.graph) == 6


def test_queue_is_fifo_and_drains_one_command_per_checkpoint(tmp_path):
    controller = DesktopController(
        runtime_root=tmp_path, frame_count=4, scenario_id="operator-report"
    )
    controller.submit(OPERATOR_MOCK_COMMANDS[0])
    backend = controller.backends["mock"]
    calls_before = len(backend.calls)

    controller.queue_command(OPERATOR_MOCK_COMMANDS[1])
    controller.queue_command("점검 상태 알려줘")

    assert controller.queued_commands == [OPERATOR_MOCK_COMMANDS[1], "점검 상태 알려줘"]
    assert controller.queued_command == OPERATOR_MOCK_COMMANDS[1]
    assert len(backend.calls) == calls_before

    controller.advance_checkpoint()
    controller.submit_queued()
    assert controller.queued_commands == ["점검 상태 알려줘"]

    controller.advance_checkpoint()
    controller.submit_queued()
    assert controller.queued_commands == []
    with pytest.raises(ValueError, match="no command is queued"):
        controller.submit_queued()


def test_cancelling_a_queued_command_touches_no_mission_state(tmp_path):
    controller = DesktopController(
        runtime_root=tmp_path, frame_count=4, scenario_id="operator-report"
    )
    controller.submit(OPERATOR_MOCK_COMMANDS[0])
    graph_before = len(controller.session.state.graph)
    turns_before = controller.session.turn_count

    controller.queue_command("첫 명령")
    controller.queue_command("둘째 명령")
    removed = controller.cancel_queued(0)

    assert removed == "첫 명령"
    assert controller.queued_commands == ["둘째 명령"]
    assert controller.session.turn_count == turns_before
    assert len(controller.session.state.graph) == graph_before
    with pytest.raises(ValueError, match="no queued command at index"):
        controller.cancel_queued(5)


@pytest.mark.parametrize("mode", ["", "LIVE", "fake", None])
def test_mode_is_strict(mode, tmp_path):
    controller = _controller(tmp_path)
    with pytest.raises(ValueError, match="mode"):
        controller.set_mode(mode)


def test_execution_requires_a_committed_plan(tmp_path):
    controller = _controller(tmp_path)
    with pytest.raises(ValueError, match="mission and plan"):
        controller.advance_checkpoint()


def test_continuous_runtime_interpolates_between_task_completion_boundaries(tmp_path):
    controller = DesktopController(
        runtime_root=tmp_path, frame_count=4, scenario_id="reference"
    )
    controller.submit(MOCK_COMMANDS[0])

    runtime = ContinuousRuntime(controller)
    opening = runtime.start()
    assert opening.boundary is not None  # first segment committed
    assert opening.frame is not None
    seg_end = runtime._segment.end_time

    mid = runtime.advance_to((opening.sim_time + seg_end) / 2)
    assert mid.boundary is None  # still inside the segment, nothing committed
    assert opening.sim_time < mid.sim_time < seg_end
    assert mid.frame.simulation_time == mid.sim_time


def test_continuous_runtime_reaches_a_terminal_regardless_of_tick_size(tmp_path):
    graphs = []
    for step in (1.0, 7.0, 40.0):
        controller = DesktopController(
            runtime_root=tmp_path / f"s{step}", frame_count=4, scenario_id="reference"
        )
        controller.submit(MOCK_COMMANDS[0])
        runtime, ticks = _run_continuous(controller, step=step)

        assert runtime.finished
        assert ticks[-1].finished
        assert controller.session.phase.value == "EXECUTED"
        assert controller.session.execution.termination.value == "COMPLETED"
        graphs.append(controller.session.execution.makespan)

    assert len(set(round(m, 6) for m in graphs)) == 1  # tick size cannot move state


def test_continuous_runtime_applies_one_queued_command_at_the_next_boundary(tmp_path):
    controller = DesktopController(
        runtime_root=tmp_path, frame_count=4, scenario_id="operator-report"
    )
    controller.submit(OPERATOR_MOCK_COMMANDS[0])
    turns_before = controller.session.turn_count

    runtime = ContinuousRuntime(controller)
    runtime.start()
    runtime.advance_to(runtime.sim_time + 2.0)
    controller.queue_command(OPERATOR_MOCK_COMMANDS[1])

    applied = None
    guard = 0
    while runtime.active and applied is None and guard < 400:
        tick = runtime.advance_to(runtime.sim_time + 3.0)
        applied = tick.queued_result
        guard += 1

    assert applied is not None
    assert applied.outcome.value == "COMMITTED"
    assert controller.queued_commands == []
    assert controller.session.turn_count == turns_before + 1


def test_district_latent_fire_profile_wires_a_seeded_field(tmp_path):
    from scenarios.latent import SimulatedFireField

    controller = DesktopController(
        runtime_root=tmp_path, frame_count=4, scenario_id="district-latent-fire"
    )

    assert controller.mode == "live"
    assert isinstance(controller.observation_source, SimulatedFireField)
    assert controller.fixture_id == "district-latent-fire-v1"
    field = controller.observation_source.fire_field
    assert len(field.zone_ids) == 2
    assert set(field.zone_ids) <= set(controller.session.scene.zones)
    # the field is not part of the world the LLM plans against
    assert field.field_id not in controller.session.context_for_llm()


def _attach_fire_field(controller, zone_id):
    import yaml

    from scenarios.latent import SimulatedFireField, load_latent_fire_field

    spec = controller.runtime_root / "field.yaml"
    spec.write_text(
        yaml.safe_dump(
            {"field_id": "gate-test", "seed": 1, "count": 1, "candidate_zones": [zone_id]}
        )
    )
    field = load_latent_fire_field(spec, controller.session.scene)
    controller.observation_source = SimulatedFireField(field)
    return field


def test_continuous_runtime_halts_when_a_fire_stays_undecided_past_a_boundary(tmp_path):
    from core.enums import TaskType
    from interaction.observe import ApprovalDecision

    controller = DesktopController(
        runtime_root=tmp_path, frame_count=4, scenario_id="operator-report"
    )
    controller.submit(OPERATOR_MOCK_COMMANDS[0])
    _attach_fire_field(controller, "ZONE_A")

    runtime, ticks = _run_continuous(controller, step=6.0)

    assert not runtime.finished and runtime.halted  # nobody answered, so it stopped
    assert controller.pending_fire_approval is not None
    assert controller.pending_fire_approval.zone_id == "ZONE_A"
    assert "AWAITING_APPROVAL" in [
        e.outcome for e in controller.session.event_log
        if isinstance(e, IncidentObservationAudit)
    ]
    # graph is untouched while the fire is held
    assert "FIRE_SITE_1" not in controller.session.scene.incidents

    # record the answer; still not applied until the next boundary
    controller.record_fire_decision(
        decision=ApprovalDecision.APPROVE, response_up_to=TaskType.GROUND_SUPPRESSION
    )
    assert controller.pending_fire_approval is None
    assert "FIRE_SITE_1" not in controller.session.scene.incidents

    runtime2, ticks2 = _run_continuous(controller, step=6.0)
    assert runtime2.finished
    assert "FIRE_SITE_1" in controller.session.scene.incidents
    assert controller.session.execution.termination.value == "COMPLETED"


def test_a_fire_answered_within_its_grace_segment_never_stops_the_clock(tmp_path):
    from core.enums import TaskType
    from interaction.observe import ApprovalDecision

    controller = DesktopController(
        runtime_root=tmp_path, frame_count=4, scenario_id="operator-report"
    )
    controller.submit(OPERATOR_MOCK_COMMANDS[0])
    _attach_fire_field(controller, "ZONE_A")

    runtime = ContinuousRuntime(controller)
    runtime.start()
    answered = False
    guard = 0
    while runtime.active and guard < 400:
        runtime.advance_to(runtime.sim_time + 4.0)
        if not answered and controller.pending_fire_approval is not None:
            controller.record_fire_decision(
                decision=ApprovalDecision.APPROVE,
                response_up_to=TaskType.GROUND_SUPPRESSION,
            )
            answered = True
        guard += 1

    assert answered
    assert runtime.finished and not runtime.halted  # never had to stop
    assert "FIRE_SITE_1" in controller.session.scene.incidents
    assert controller.session.execution.termination.value == "COMPLETED"


def test_continuous_runtime_decline_leaves_the_mission_unchanged(tmp_path):
    from interaction.observe import ApprovalDecision

    controller = DesktopController(
        runtime_root=tmp_path, frame_count=4, scenario_id="operator-report"
    )
    controller.submit(OPERATOR_MOCK_COMMANDS[0])
    _attach_fire_field(controller, "ZONE_A")

    _run_continuous(controller, step=6.0)
    graph_len = len(controller.session.state.graph)

    controller.record_fire_decision(decision=ApprovalDecision.DECLINE)
    assert controller.pending_fire_approval is None

    runtime, _ = _run_continuous(controller, step=6.0)
    assert runtime.finished
    assert len(controller.session.state.graph) == graph_len
    assert "FIRE_SITE_1" not in controller.session.scene.incidents
    assert controller.session.execution.termination.value == "COMPLETED"


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
    assert len(controller.session.state.graph) == 6
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
    assert len(controller.session.state.graph) == 6


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
