"""P4 completion gate (RESEARCH_CONTRACT.md §15): 2D executor end-to-end.

- reference mission runs to completion, violations == 0
- internal MissionState satisfies the §10 assignment invariant afterwards
- deterministic
- premature-deadlock minimal repro (single agent, A->B chain) — §14
- a genuine deadlock terminates and is reported; STEP_LIMIT is distinct
- a RUNNING agent's residual-path bid does not double-count its current task
"""

import math
from pathlib import Path

import pytest

from core.enums import PlatformKind, TaskStatus, TaskType
from core.mission_state import MissionState
from execution.executor import SimExecutor, Termination
from scenarios.compiler import compile_reference_graph
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
        scene, list(specs), [tuple(e) for e in edges]
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
            if tt in (TaskType.GROUND_INSPECTION, TaskType.GROUND_SUPPRESSION)
            else PlatformKind.UAV
        )
        assert kind[aid] is want


def test_reference_workload_is_balanced_and_uses_response_uavs(ref_state, scene):
    # With availability-aware bidding (D-013) the rolling executor spreads the
    # heterogeneous work: every agent is used, scouts 3 each, responders 1 each,
    # UGVs 2 each.
    r = SimExecutor(ref_state, scene).run()
    assert r.idle_agents == []
    assert r.workload == {"S1": 3, "S2": 3, "R1": 1, "R2": 1, "G1": 2, "G2": 2}


def test_departure_is_never_before_predecessor_completes(scene):
    # Synthetic chain across two different positions: THERMAL_RECON at the
    # incident, SUPPRESSANT_DROP done by a *different* agent starting from the
    # depot, so there is a real post-ready travel leg.
    graph = compile_reference_graph(scene, [TR_F1, SD_F1], [(TR_F1, SD_F1)])
    state = MissionState(
        graph, {a.agent_id: a for a in scene.fleet if a.agent_id in {"S1", "R1"}}
    )
    r = SimExecutor(state, scene).run()
    tr_done = r.task_completion["THERMAL_RECON__FIRE_SITE_1"]
    sd_dep = r.task_departure["SUPPRESSANT_DROP__FIRE_SITE_1"]
    sd_start = r.task_start["SUPPRESSANT_DROP__FIRE_SITE_1"]
    assert sd_dep >= tr_done - 1e-6  # R1 did not leave before the task was READY

    # departure -> on-site start gap is exactly R1's travel leg (UAV, Euclidean)
    r1 = next(a for a in scene.fleet if a.agent_id == "R1")
    sd = graph["SUPPRESSANT_DROP__FIRE_SITE_1"]
    leg = math.dist(r1.position, sd.position) / r1.speed
    assert sd_start - sd_dep == pytest.approx(leg)


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


# -- residual-path bidding through the real executor (D-012/D-013) -------


def _mid_task_executor(scene, r1_remaining: float):
    """SimExecutor with R1 mid-task on SUPPRESSANT_DROP_F1 (landing == the new
    THERMAL_RECON_F1 position), R2 idle 70 m from the new task."""
    graph = compile_reference_graph(
        scene,
        [(TaskType.SUPPRESSANT_DROP, "FIRE_SITE_1"), (TaskType.THERMAL_RECON, "FIRE_SITE_1")],
        [],
    )
    fleet = {a.agent_id: a for a in scene.fleet if a.agent_id in {"R1", "R2"}}
    ex = SimExecutor(MissionState(graph, fleet), scene)
    running_tid, new_tid = "SUPPRESSANT_DROP__FIRE_SITE_1", "THERMAL_RECON__FIRE_SITE_1"

    ex.now = 100.0
    ex.sim["R1"].current = running_tid
    ex.sim["R1"].finish_at = ex.now + r1_remaining
    ex.agents["R1"].path = [running_tid]
    ex.agents["R1"].current_task = running_tid
    ex.graph[running_tid].status = TaskStatus.RUNNING
    ex.graph[running_tid].assigned_agent = "R1"
    ex.assignments[running_tid] = "R1"
    ex.winning_bids[running_tid] = 5.0

    np = ex.graph[new_tid].position
    ex.agents["R2"].position = (np[0] - 70.0, np[1])
    ex.graph[new_tid].status = TaskStatus.READY
    return ex, new_tid


def test_residual_bid_near_agent_wins_when_it_finishes_soon(scene):
    ex, new_tid = _mid_task_executor(scene, r1_remaining=2.0)
    ex._run_epoch()
    assert ex.assignments[new_tid] == "R1"
    # the RUNNING task is back at the head of R1's path, not double-listed
    assert ex.agents["R1"].path[0] == "SUPPRESSANT_DROP__FIRE_SITE_1"
    assert ex.agents["R1"].path.count("SUPPRESSANT_DROP__FIRE_SITE_1") == 1


def test_residual_bid_far_available_agent_wins_when_near_agent_is_busy_long(scene):
    ex, new_tid = _mid_task_executor(scene, r1_remaining=1000.0)
    ex._run_epoch()
    assert ex.assignments[new_tid] == "R2"


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
    assert r.agent_utilization == {}  # not a usable figure for STEP_LIMIT (D-014)


def test_completion_on_the_final_step_reports_completed(scene):
    # A one-task mission that finishes exactly as the step budget runs out must
    # not be misreported as STEP_LIMIT.
    graph = compile_reference_graph(scene, [(TR_F1[0], "FIRE_SITE_1")], [])
    state = MissionState(graph, {a.agent_id: a for a in scene.fleet if a.agent_id == "S1"})
    r = SimExecutor(state, scene).run(max_steps=2)
    assert r.completed == ["THERMAL_RECON__FIRE_SITE_1"]
    assert r.unfinished_tasks == []
    assert r.termination is Termination.COMPLETED
