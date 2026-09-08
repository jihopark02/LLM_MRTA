"""P3 completion gate (RESEARCH_CONTRACT.md §15): reference fixture allocation.

- capability / precedence violations == 0
- every UGV leg uses route-graph distance, not the Euclidean shortcut
- deterministic re-run
"""

import math
from pathlib import Path

import pytest

from allocation.allocate import allocate
from core.enums import PlatformKind, TaskType
from core.mission_state import MissionState
from scenarios.fixture import load_reference_fixture
from scenarios.scene import load_scene

SCEN = Path(__file__).parents[1] / "scenarios"


@pytest.fixture
def scene():
    return load_scene(SCEN / "industrial_park.yaml")


@pytest.fixture
def state(scene):
    graph = load_reference_fixture(SCEN / "reference_fixture.yaml").graph
    return MissionState(graph, {a.agent_id: a for a in scene.fleet})


def test_reference_fixture_fully_allocated_with_no_violations(state, scene):
    r = allocate(state, scene)
    assert r.allocation_success
    assert r.unassigned_tasks == []
    assert r.capability_violations == []
    assert r.precedence_violations == []
    assert len(r.assignments) == 8


def test_platforms_match_task_types(state, scene):
    r = allocate(state, scene)
    kind = {a.agent_id: a.platform_kind for a in scene.fleet}
    for task_id, agent_id in r.assignments.items():
        tt = state.graph[task_id].task_type
        if tt in (TaskType.GROUND_INSPECTION, TaskType.GROUND_SUPPRESSION):
            assert kind[agent_id] is PlatformKind.UGV
        else:
            assert kind[agent_id] is PlatformKind.UAV


def test_every_uav_carries_work(state, scene):
    # D-060: the 3 UAVs are identical; CBBA still spreads the aerial tasks
    # rather than piling them on one airframe.
    r = allocate(state, scene)
    uav_ids = {a.agent_id for a in scene.fleet if a.platform_kind is PlatformKind.UAV}
    assert all(r.workload[u] >= 1 for u in uav_ids)


def test_ugv_distance_is_route_graph_not_euclidean(state, scene):
    r = allocate(state, scene)
    assert r.ugv_route_distance > 0

    # Recompute the UGV legs by hand from the assignment and compare.
    rg = scene.route_graph
    route_total = 0.0
    euclid_total = 0.0
    for agent_id in ("G1", "G2"):
        node = scene.agent_access_nodes[agent_id]
        pos = rg.position(node)
        legs = sorted(
            (tid for tid, aid in r.assignments.items() if aid == agent_id),
            key=lambda t: r.task_start[t],
        )
        for tid in legs:
            inc = state.graph[tid].target
            to_node = scene.incidents[inc].access_node
            route_total += rg.shortest_path_distance(node, to_node)
            euclid_total += math.dist(pos, state.graph[tid].position)
            node, pos = to_node, rg.position(to_node)

    assert r.ugv_route_distance == pytest.approx(route_total)
    assert route_total != pytest.approx(euclid_total)


def test_allocation_is_deterministic(state, scene):
    scene2 = load_scene(SCEN / "industrial_park.yaml")
    graph2 = load_reference_fixture(SCEN / "reference_fixture.yaml").graph
    state2 = MissionState(graph2, {a.agent_id: a for a in scene2.fleet})

    a = allocate(state, scene)
    b = allocate(state2, scene2)
    assert a.assignments == b.assignments
    assert a.winning_bids == b.winning_bids
    assert a.consensus_rounds == b.consensus_rounds
    assert a.estimated_makespan == pytest.approx(b.estimated_makespan)


def test_barrier_no_travel_before_task_is_ready(state, scene):
    r = allocate(state, scene)
    # GROUND_SUPPRESSION starts strictly after GROUND_INSPECTION completes PLUS a
    # nonzero dwell (the UGV cannot pre-position during epoch 1).
    for inc in ("FIRE_SITE_1", "FIRE_SITE_2"):
        gi_done = r.task_completion[f"GROUND_INSPECTION__{inc}"]
        gs_start = r.task_start[f"GROUND_SUPPRESSION__{inc}"]
        assert gs_start >= gi_done - 1e-6  # successor never starts before predecessor done


def test_utilization_excludes_waiting(state, scene):
    r = allocate(state, scene)
    # busy = travel + dwell only, so utilization is well below 1 for agents that
    # wait between waves.
    assert all(0.0 <= u < 1.0 for u in r.agent_utilization.values())
    assert min(r.agent_utilization.values()) < 0.5  # some agent waits between waves


def test_frontier_stall_stops_immediately(scene, tmp_path):
    # A fixture whose sole task needs a capability no agent has -> stall.
    fx = tmp_path / "stall.yaml"
    fx.write_text(
        "fixture_id: stall\nscene: industrial_park\n"
        "tasks:\n  - {type: GROUND_SUPPRESSION, target: FIRE_SITE_1, priority: 9}\n"
        "  - {type: GROUND_INSPECTION, target: FIRE_SITE_1, priority: 9}\n"
        "edges:\n  - [GROUND_INSPECTION:FIRE_SITE_1, GROUND_SUPPRESSION:FIRE_SITE_1]\n"
    )
    graph = load_reference_fixture(fx).graph
    # remove every UGV so the ground chain can never be won
    fleet = [a for a in scene.fleet if a.platform_kind is PlatformKind.UAV]
    st = MissionState(graph, {a.agent_id: a for a in fleet})
    r = allocate(st, scene, max_epochs=5)
    assert "GROUND_SUPPRESSION__FIRE_SITE_1" in r.unassigned_tasks
    assert "GROUND_INSPECTION__FIRE_SITE_1" in r.unassigned_tasks
    assert not r.allocation_success
    # the only READY task (GROUND_INSPECTION) has no eligible bidder, so epoch 1
    # auctions it once and the run stops — not re-auctioned 5x despite max_epochs.
    assert r.consensus_rounds == [2]


def test_ugv_marginal_bid_uses_route_distance(state, scene):
    from allocation.scoring import DEFAULT_LAMBDA, marginal_score
    from scenarios.compiler import compile_task

    g1 = next(a for a in scene.fleet if a.agent_id == "G1")
    gi = compile_task(scene, TaskType.GROUND_INSPECTION, "FIRE_SITE_1", 8)
    node = scene.incidents["FIRE_SITE_1"].access_node

    route_time = scene.route_graph.shortest_path_distance("R_DEPOT", node) / g1.speed
    expected = (DEFAULT_LAMBDA ** (route_time + gi.duration)) * gi.priority
    gain, n = marginal_score(g1, gi, [], scene)
    assert gain == pytest.approx(expected)
    assert n == 0

    euclid_time = math.dist(scene.route_graph.position("R_DEPOT"), gi.position) / g1.speed
    euclid_bid = (DEFAULT_LAMBDA ** (euclid_time + gi.duration)) * gi.priority
    assert gain != pytest.approx(euclid_bid)


def test_bundle_and_path_postcondition_after_epoch(scene):
    from dataclasses import replace

    from allocation.cbba import run_epoch
    from core.enums import TaskStatus
    from scenarios.compiler import compile_task

    tasks = {}
    for tt, target in [
        (TaskType.AREA_RECON, "ZONE_A"),
        (TaskType.AREA_RECON, "ZONE_B"),
        (TaskType.GROUND_INSPECTION, "FIRE_SITE_1"),
    ]:
        t = compile_task(scene, tt, target, 5)
        t.status = TaskStatus.READY
        tasks[t.task_id] = t
    agents = {a.agent_id: replace(a, bundle=[], path=[]) for a in scene.fleet}
    run_epoch(tasks, agents, scene)

    seen: set[str] = set()
    for a in agents.values():
        assert set(a.bundle) == set(a.path)  # same task set
        assert len(a.bundle) == len(set(a.bundle))  # no dupes
        assert not (seen & set(a.bundle))  # single owner
        seen |= set(a.bundle)
        assert a.current_task is None


def test_frontier_rolls_epoch_by_epoch(state, scene):
    r = allocate(state, scene)
    # GROUND_INSPECTION completes before its GROUND_SUPPRESSION starts (precedence).
    for inc in ("FIRE_SITE_1", "FIRE_SITE_2"):
        assert (
            r.task_completion[f"GROUND_INSPECTION__{inc}"]
            <= r.task_start[f"GROUND_SUPPRESSION__{inc}"] + 1e-6
        )
    assert len(r.consensus_rounds) == 2  # 2 frontier waves
