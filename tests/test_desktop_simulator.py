"""P11 native simulator view gates (§21)."""

# ruff: noqa: E402 -- the offscreen platform must be selected before Qt imports.

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from demo.animation import build_playback_spec
from demo.visualization import plan_map_spec
from desktop.simulator import MissionSimulatorWindow
from execution.executor import SimExecutor
from interaction.session import fresh_session_state
from scenarios.fixture import load_reference_fixture


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def _plan_spec():
    fixture = load_reference_fixture()
    from allocation.allocate import allocate

    state = fresh_session_state(fixture.graph, fixture.scene)
    return plan_map_spec(fixture.scene, state.graph, allocate(state, fixture.scene))


def _playback():
    fixture = load_reference_fixture()
    executor = SimExecutor(
        fresh_session_state(fixture.graph, fixture.scene), fixture.scene
    )
    before = executor.checkpoint()
    after = executor.advance_to_next_completion().checkpoint
    return build_playback_spec(fixture.scene, before, after, frame_count=4)


def _drain_until(app, condition, timeout=1.0):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.002)
    assert condition()


def test_static_spec_is_drawn_without_reading_a_session(qt_app):
    window = MissionSimulatorWindow()
    spec = _plan_spec()
    window.show_spec(spec)

    assert window.canvas.spec is spec
    assert window.canvas.frame is None
    assert "PLAN" in window.header.text()
    window.canvas.grab()  # forces the offscreen paint path
    window.shutdown()


def test_playback_uses_every_frozen_frame_and_emits_boundaries(qt_app):
    window = MissionSimulatorWindow()
    playback = _playback()
    events = []
    window.playback_started.connect(lambda: events.append("start"))
    window.playback_finished.connect(lambda: events.append("finish"))

    window.play(playback, wall_seconds=0.01)
    assert window.is_playing
    assert events == ["start"]
    _drain_until(qt_app, lambda: not window.is_playing)

    assert events == ["start", "finish"]
    assert window.canvas.frame is playback.frames[-1]
    assert window.canvas.spec is playback.frames[-1].map_spec
    window.shutdown()


def test_closing_the_simulator_hides_it_without_destroying_its_spec(qt_app):
    window = MissionSimulatorWindow()
    spec = _plan_spec()
    window.show_spec(spec)
    window.show()
    qt_app.processEvents()

    window.close()
    qt_app.processEvents()

    assert not window.isVisible()
    assert window.canvas.spec is spec
    window.show()
    qt_app.processEvents()
    assert window.isVisible()
    window.shutdown()
