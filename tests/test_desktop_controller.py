"""P11 Qt-independent presentation controller gates (§21)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from demo.mock_script import MOCK_COMMANDS
from desktop.controller import DesktopController
from interaction.audit import CheckpointAudit


def _controller(tmp_path):
    return DesktopController(runtime_root=tmp_path, frame_count=4)


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


@pytest.mark.parametrize("mode", ["", "LIVE", "fake", None])
def test_mode_is_strict(mode, tmp_path):
    controller = _controller(tmp_path)
    with pytest.raises(ValueError, match="mode"):
        controller.set_mode(mode)


def test_execution_requires_a_committed_plan(tmp_path):
    controller = _controller(tmp_path)
    with pytest.raises(ValueError, match="mission and plan"):
        controller.advance_checkpoint()
