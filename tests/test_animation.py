"""P10 deterministic checkpoint-segment playback gates (§20, D-046)."""

import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from core.route_graph import RouteGraph
from demo.animation import _ugv_position, build_playback_spec
from demo.visualization import render_playback_frame, runtime_map_spec
from execution.executor import SimExecutor
from interaction.session import fresh_session_state
from scenarios.fixture import load_reference_fixture
from validator.hashing import pre_state_hash, scene_hash


def _first_segment():
    fixture = load_reference_fixture()
    state = fresh_session_state(fixture.graph, fixture.scene)
    executor = SimExecutor(state, fixture.scene)
    before = executor.checkpoint()
    advance = executor.advance_to_next_completion()
    return fixture.scene, before, advance.checkpoint


def _fingerprint(checkpoint):
    return (
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
        pre_state_hash(checkpoint._work),
    )


def test_same_checkpoints_and_frame_count_make_the_same_spec():
    scene, before, after = _first_segment()
    assert build_playback_spec(scene, before, after, frame_count=9) == build_playback_spec(
        scene, before, after, frame_count=9
    )


def test_frames_cover_the_exact_interval_and_agent_set():
    scene, before, after = _first_segment()
    spec = build_playback_spec(scene, before, after, frame_count=5)

    assert spec.start_time == before.now
    assert spec.end_time == after.now
    assert [frame.progress for frame in spec.frames] == [0.0, 0.25, 0.5, 0.75, 1.0]
    assert spec.frames[0].simulation_time == before.now
    assert spec.frames[-1].simulation_time == after.now
    expected = tuple(sorted(after._work.agents))
    assert all(tuple(agent.agent_id for agent in frame.agents) == expected for frame in spec.frames)


def test_uav_moves_then_dwells_and_the_completed_agent_ends_at_the_target():
    scene, before, after = _first_segment()
    spec = build_playback_spec(scene, before, after, frame_count=9)
    task_id = "THERMAL_RECON__FIRE_SITE_1"
    samples = [
        next(agent for agent in frame.agents if agent.agent_id == "S1")
        for frame in spec.frames
    ]

    assert samples[0].activity == "TRAVEL"
    assert any(sample.activity == "DWELL" for sample in samples[1:-1])
    assert samples[-1].activity == "IDLE"
    assert samples[-1].task_id is None
    assert samples[-1].position == tuple(map(float, after._work.graph[task_id].position))
    assert len({sample.position for sample in samples}) > 2


def test_ugv_interpolation_uses_lane_weight_not_geometric_segment_length():
    fixture = load_reference_fixture()
    graph = RouteGraph()
    graph.add_node("A", (0.0, 0.0))
    graph.add_node("B", (10.0, 0.0))
    graph.add_node("C", (20.0, 0.0))
    graph.add_lane("A", "B", weight=1.0)
    graph.add_lane("B", "C", weight=3.0)
    scene = replace(fixture.scene, route_graph=graph)

    # Half the route *cost* is one unit through A-B plus one of three units
    # through B-C: one third of the second geometric segment, x=13.333...
    assert _ugv_position(scene, "A", "C", 0.5) == pytest.approx((40.0 / 3.0, 0.0))


def test_reference_ugv_really_moves_along_a_checkpoint_playback():
    fixture = load_reference_fixture()
    executor = SimExecutor(
        fresh_session_state(fixture.graph, fixture.scene), fixture.scene
    )
    observed = None
    for _ in range(20):
        before = executor.checkpoint()
        advance = executor.advance_to_next_completion()
        if advance.checkpoint.now > before.now:
            candidate = build_playback_spec(
                fixture.scene, before, advance.checkpoint, frame_count=9
            )
            active = [
                agent
                for frame in candidate.frames
                for agent in frame.agents
                if agent.agent_id in {"G1", "G2"} and agent.activity != "IDLE"
            ]
            if active:
                observed = active
                break
        if advance.execution is not None:
            break

    assert observed, "the reference execution must expose a UGV playback segment"
    assert any(agent.activity == "TRAVEL" for agent in observed)
    assert all(
        agent.task_id.startswith(("GROUND_INSPECTION", "GROUND_SUPPRESSION"))
        for agent in observed
    )


def test_last_frame_matches_completed_pose_and_keeps_other_running_activity():
    scene, before, after = _first_segment()
    spec = build_playback_spec(scene, before, after, frame_count=4)
    final = {agent.agent_id: agent for agent in spec.frames[-1].agents}
    restored = SimExecutor.from_checkpoint(after, scene)
    static = {agent.agent_id: agent.position for agent in runtime_map_spec(scene, restored).agents}

    # S1 completed at this checkpoint, so its pose is now confirmed and agrees
    # with the static Runtime map.
    assert final["S1"].activity == "IDLE"
    assert final["S1"].position == static["S1"]
    # S2 is still dwelling. P8.5's static map deliberately leaves it at the
    # last confirmed position, while P10 shows the recorded schedule pose —
    # forcing equality here would make the animated marker jump backwards.
    assert final["S2"].activity == "DWELL"
    assert final["S2"].task_id == "THERMAL_RECON__FIRE_SITE_2"
    assert final["S2"].position != static["S2"]
    assert final["S2"].position == tuple(
        map(float, after._work.graph[final["S2"].task_id].position)
    )


def test_spec_generation_does_not_mutate_scene_or_either_checkpoint():
    scene, before, after = _first_segment()
    snapshot = (_fingerprint(before), _fingerprint(after), scene_hash(scene))
    build_playback_spec(scene, before, after, frame_count=7)
    assert (_fingerprint(before), _fingerprint(after), scene_hash(scene)) == snapshot


@pytest.mark.parametrize("frame_count", [1, 0, -1, True, 2.0, "3"])
def test_invalid_frame_count_is_rejected(frame_count):
    scene, before, after = _first_segment()
    with pytest.raises(ValueError, match="frame_count"):
        build_playback_spec(scene, before, after, frame_count=frame_count)


def test_non_advancing_checkpoints_are_rejected():
    scene, before, _ = _first_segment()
    with pytest.raises(ValueError, match="later"):
        build_playback_spec(scene, before, before)


def test_spec_path_does_not_import_matplotlib():
    probe = (
        "import sys;"
        "from demo.animation import build_playback_spec;"
        "from execution.executor import SimExecutor;"
        "from interaction.session import fresh_session_state;"
        "from scenarios.fixture import load_reference_fixture;"
        "f=load_reference_fixture();e=SimExecutor(fresh_session_state(f.graph,f.scene),f.scene);"
        "b=e.checkpoint();a=e.advance_to_next_completion().checkpoint;"
        "build_playback_spec(f.scene,b,a,frame_count=3);"
        "hit=any(n=='matplotlib' or n.startswith('matplotlib.') for n in sys.modules);"
        "print('LEAK' if hit else 'CLEAN')"
    )
    done = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=Path(__file__).parents[1],
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        check=True,
    )
    assert done.stdout.strip() == "CLEAN"


def test_frame_renderer_consumes_the_spec_and_labels_activity():
    scene, before, after = _first_segment()
    frame = build_playback_spec(scene, before, after, frame_count=3).frames[1]
    figure = render_playback_frame(frame)
    try:
        assert "schedule interpolation, not telemetry" in figure.axes[0].get_title(loc="left")
        text = " ".join(item.get_text() for item in figure.axes[0].texts)
        assert "TRAVEL" in text or "DWELL" in text
    finally:
        figure.clear()
