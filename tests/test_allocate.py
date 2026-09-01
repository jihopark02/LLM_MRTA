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
    assert len(r.assignments) == 12


def test_platforms_match_task_types(state, scene):
    r = allocate(state, scene)
    kind = {a.agent_id: a.platform_kind for a in scene.fleet}
    for task_id, agent_id in r.assignments.items():
        tt = state.graph[task_id].task_type
        if tt in (TaskType.GROUND_INSPECTION, TaskType.HAZARD_MARKER_DEPLOY):
            assert kind[agent_id] is PlatformKind.UGV
        else:
            assert kind[agent_id] is PlatformKind.UAV
        if tt is TaskType.SUPPRESSANT_DROP:
            assert agent_id in {"R1", "R2"}


def test_response_uavs_are_used(state, scene):
    r = allocate(state, scene)
    assert r.workload["R1"] + r.workload["R2"] == 2  # both SUPPRESSANT_DROP tasks


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


def test_frontier_rolls_epoch_by_epoch(state, scene):
    r = allocate(state, scene)
    # THERMAL_RECON completes before its SUPPRESSANT_DROP starts (precedence).
    for inc in ("FIRE_SITE_1", "FIRE_SITE_2"):
        assert (
            r.task_completion[f"THERMAL_RECON__{inc}"]
            <= r.task_start[f"SUPPRESSANT_DROP__{inc}"] + 1e-6
        )
    assert len(r.consensus_rounds) == 4  # 4 frontier waves
