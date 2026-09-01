"""P4 completion gate (RESEARCH_CONTRACT.md §15): 2D executor end-to-end.

- reference mission runs to completion, violations == 0
- internal MissionState satisfies the §10 assignment invariant afterwards
- deterministic
- premature-deadlock minimal repro (single agent, A->B chain) — §14
- a genuine deadlock terminates and is reported; STEP_LIMIT is distinct
- a RUNNING agent's residual-path bid does not double-count its current task
"""

from dataclasses import replace
from pathlib import Path

import pytest

from core.enums import PlatformKind, TaskStatus, TaskType
from core.mission_state import MissionState
from execution.executor import SimExecutor, Termination
from scenarios.compiler import compile_reference_graph, compile_task
from scenarios.fixture import load_reference_fixture
from scenarios.scene import load_scene
from validator.patch_apply import _assignment_invariant_errors

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
    ex = SimExecutor(ref_state, scene)
    r = ex.run()
    assert r.termination is Termination.COMPLETED
    assert len(r.completed) == 12
    assert r.capability_violations == []
    assert r.precedence_violations == []
    assert r.unfinished_tasks == []
    # executor works on a clone — the caller's state is untouched
    assert all(t.status is not TaskStatus.COMPLETED for t in ref_state.graph.tasks)


def test_completed_state_satisfies_assignment_invariant(ref_state, scene):
    ex = SimExecutor(ref_state, scene)
    ex.run()
    assert _assignment_invariant_errors(ex.work) == []
    for agent in ex.work.agents.values():
        assert agent.current_task is None
        assert agent.bundle == [] and agent.path == []
    for t in ex.work.graph.tasks:
        assert t.assigned_agent is None


def test_platforms_match_task_types_and_route_distance(ref_state, scene):
    r = SimExecutor(ref_state, scene).run()
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


def test_departure_is_never_before_predecessor_completes(scene):
    # Synthetic chain across two different positions: THERMAL_RECON at the
    # incident, SUPPRESSANT_DROP done by a *different* agent starting from the
    # depot, so there is a real post-ready travel leg.
    graph = compile_reference_graph(
        scene, [(*TR_F1, 5), (*SD_F1, 5)], [(TR_F1, SD_F1)]
    )
    state = MissionState(graph, {a.agent_id: a for a in scene.fleet if a.agent_id in {"S1", "R1"}})
    r = SimExecutor(state, scene).run()
    tr_done = r.task_completion["THERMAL_RECON__FIRE_SITE_1"]
    sd_departure = r.task_departure["SUPPRESSANT_DROP__FIRE_SITE_1"]
    sd_start = r.task_start["SUPPRESSANT_DROP__FIRE_SITE_1"]
    assert sd_departure >= tr_done - 1e-6           # did not leave early
    assert sd_start > sd_departure + 1.0           # a real travel leg followed


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


# -- residual-path bidding (D-012) ----------------------------------


def test_running_agent_bid_excludes_its_current_task(scene):
    from allocation.cbba import run_epoch

    # R1 is mid-task; its landing position coincides with a new task. R2 is far.
    # A correct residual-path bid lets R1 (already there) win; the old bug
    # (double-counting the running task) handed it to R2.
    new = compile_task(scene, TaskType.THERMAL_RECON, "FIRE_SITE_1", 9)
    new.status = TaskStatus.READY
    running = compile_task(scene, TaskType.SUPPRESSANT_DROP, "FIRE_SITE_1", 9)

    agents = {}
    r1 = replace(next(a for a in scene.fleet if a.agent_id == "R1"),
                 position=running.position, bundle=[], path=[])
    r2 = replace(next(a for a in scene.fleet if a.agent_id == "R2"),
                 position=(running.position[0] - 70.0, running.position[1]), bundle=[], path=[])
    agents["R1"], agents["R2"] = r1, r2

    result = run_epoch({new.task_id: new}, agents, scene, frontier=[new.task_id])
    assert result.winners[new.task_id] == "R1"


# -- §14 premature-deadlock minimal repro -----------------------------


def test_single_agent_chain_does_not_false_deadlock(scene):
    state = _state(scene, [TR_F1, SD_F1], [(TR_F1, SD_F1)], {"R1"})
    r = SimExecutor(state, scene).run()
    assert r.termination is Termination.COMPLETED
    assert set(r.completed) == {"THERMAL_RECON__FIRE_SITE_1", "SUPPRESSANT_DROP__FIRE_SITE_1"}
    assert r.assignments == {
        "THERMAL_RECON__FIRE_SITE_1": "R1",
        "SUPPRESSANT_DROP__FIRE_SITE_1": "R1",
    }
    assert (
        r.task_departure["SUPPRESSANT_DROP__FIRE_SITE_1"]
        >= r.task_completion["THERMAL_RECON__FIRE_SITE_1"] - 1e-6
    )


# -- genuine deadlock vs step limit --------------------------------


def test_genuine_deadlock_is_reported_and_terminates(scene):
    state = _state(scene, [TR_F1, SD_F1], [(TR_F1, SD_F1)], {"G1"})  # UGV only
    r = SimExecutor(state, scene).run(max_steps=100)
    assert r.termination is Termination.DEADLOCK
    assert r.deadlocked
    assert set(r.unfinished_tasks) == {
        "THERMAL_RECON__FIRE_SITE_1",
        "SUPPRESSANT_DROP__FIRE_SITE_1",
    }
    assert r.completed == []


def test_partial_progress_then_deadlock(scene):
    state = _state(scene, [TR_F1, SD_F1], [(TR_F1, SD_F1)], {"S1"})  # no Response UAV
    r = SimExecutor(state, scene).run(max_steps=100)
    assert r.completed == ["THERMAL_RECON__FIRE_SITE_1"]
    assert r.termination is Termination.DEADLOCK
    assert r.unfinished_tasks == ["SUPPRESSANT_DROP__FIRE_SITE_1"]


def test_step_limit_is_not_a_deadlock(ref_state, scene):
    r = SimExecutor(ref_state, scene).run(max_steps=2)
    assert r.termination is Termination.STEP_LIMIT
    assert not r.deadlocked
    assert r.unfinished_tasks  # some tasks left, but it is not a deadlock
