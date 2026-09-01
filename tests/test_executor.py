"""P4 completion gate (RESEARCH_CONTRACT.md §15): 2D executor end-to-end.

- reference mission runs to completion, violations == 0
- deterministic
- premature-deadlock minimal repro (single agent, A->B chain) — §14
- a genuine deadlock terminates and is reported, not hung
"""

from pathlib import Path

import pytest

from core.enums import PlatformKind, TaskStatus, TaskType
from core.mission_state import MissionState
from execution.executor import SimExecutor
from scenarios.compiler import compile_reference_graph
from scenarios.fixture import load_reference_fixture
from scenarios.scene import load_scene

SCEN = Path(__file__).parents[1] / "scenarios"

TR_F1 = (TaskType.THERMAL_RECON, "FIRE_SITE_1")
SD_F1 = (TaskType.SUPPRESSANT_DROP, "FIRE_SITE_1")


@pytest.fixture
def scene():
    return load_scene(SCEN / "industrial_park.yaml")


@pytest.fixture
def ref_state(scene):
    graph = load_reference_fixture(SCEN / "reference_fixture.yaml").graph
    return MissionState(graph, {a.agent_id: a for a in scene.fleet})


def _state(scene, specs, edges, agent_ids):
    graph = compile_reference_graph(
        scene, [(tt, tgt, 5) for tt, tgt in specs], [tuple(e) for e in edges]
    )
    fleet = {a.agent_id: a for a in scene.fleet if a.agent_id in agent_ids}
    return MissionState(graph, fleet)


# -- reference mission --------------------------------------------------


def test_reference_mission_runs_to_completion(ref_state, scene):
    r = SimExecutor(ref_state, scene).run()
    assert not r.deadlocked
    assert len(r.completed) == 12
    assert r.capability_violations == []
    assert r.precedence_violations == []
    # executor works on a clone — the caller's state is untouched
    assert all(t.status is not TaskStatus.COMPLETED for t in ref_state.graph.tasks)


def test_executor_uses_all_agents_and_route_distance(ref_state, scene):
    r = SimExecutor(ref_state, scene).run()
    assert r.idle_agents == []
    assert r.ugv_route_distance > 0
    kind = {a.agent_id: a.platform_kind for a in scene.fleet}
    for tid, aid in r.assignments.items():
        tt = ref_state.graph[tid].task_type
        want = (
            PlatformKind.UGV
            if tt in (TaskType.GROUND_INSPECTION, TaskType.HAZARD_MARKER_DEPLOY)
            else PlatformKind.UAV
        )
        assert kind[aid] is want


def test_executor_precedence_gap_is_real_travel(ref_state, scene):
    r = SimExecutor(ref_state, scene).run()
    for inc in ("FIRE_SITE_1", "FIRE_SITE_2"):
        for a, b in (
            ("THERMAL_RECON", "SUPPRESSANT_DROP"),
            ("SUPPRESSANT_DROP", "GROUND_INSPECTION"),
            ("GROUND_INSPECTION", "HAZARD_MARKER_DEPLOY"),
        ):
            done = r.task_completion[f"{a}__{inc}"]
            start = r.task_start[f"{b}__{inc}"]
            assert start >= done - 1e-6


def test_executor_is_deterministic(scene):
    def run():
        graph = load_reference_fixture(SCEN / "reference_fixture.yaml").graph
        sc = load_scene(SCEN / "industrial_park.yaml")
        st = MissionState(graph, {a.agent_id: a for a in sc.fleet})
        return SimExecutor(st, sc).run()

    a, b = run(), run()
    assert a.assignments == b.assignments
    assert a.consensus_rounds == b.consensus_rounds
    assert a.makespan == pytest.approx(b.makespan)


# -- §14 premature-deadlock minimal repro -----------------------------


def test_single_agent_chain_does_not_false_deadlock(scene):
    # R1 alone must do THERMAL_RECON then, after it completes and B is
    # recomputed READY, SUPPRESSANT_DROP. A stale ready-set would call this a
    # deadlock right after THERMAL_RECON finishes.
    state = _state(scene, [TR_F1, SD_F1], [(TR_F1, SD_F1)], {"R1"})
    r = SimExecutor(state, scene).run()
    assert not r.deadlocked
    assert set(r.completed) == {"THERMAL_RECON__FIRE_SITE_1", "SUPPRESSANT_DROP__FIRE_SITE_1"}
    assert r.assignments == {
        "THERMAL_RECON__FIRE_SITE_1": "R1",
        "SUPPRESSANT_DROP__FIRE_SITE_1": "R1",
    }
    assert (
        r.task_start["SUPPRESSANT_DROP__FIRE_SITE_1"]
        >= r.task_completion["THERMAL_RECON__FIRE_SITE_1"] - 1e-6
    )


# -- genuine deadlock ------------------------------------------------


def test_genuine_deadlock_is_reported_and_terminates(scene):
    # Only a UGV in the fleet; THERMAL_RECON needs THERMAL_SENSOR -> unassignable,
    # so SUPPRESSANT_DROP can never become READY.
    state = _state(scene, [TR_F1, SD_F1], [(TR_F1, SD_F1)], {"G1"})
    r = SimExecutor(state, scene).run(max_steps=100)
    assert r.deadlocked
    assert "THERMAL_RECON__FIRE_SITE_1" in r.deadlock_tasks
    assert "SUPPRESSANT_DROP__FIRE_SITE_1" in r.deadlock_tasks
    assert r.completed == []


def test_partial_progress_then_deadlock(scene):
    # THERMAL_RECON is doable (S1), its successor SUPPRESSANT_DROP is not
    # (no Response UAV) -> one task completes, then a reported deadlock.
    state = _state(scene, [TR_F1, SD_F1], [(TR_F1, SD_F1)], {"S1"})
    r = SimExecutor(state, scene).run(max_steps=100)
    assert r.completed == ["THERMAL_RECON__FIRE_SITE_1"]
    assert r.deadlocked
    assert r.deadlock_tasks == ["SUPPRESSANT_DROP__FIRE_SITE_1"]
