"""Extended presentation scene (RESEARCH_CONTRACT.md §3.1, D-059).

This scene is NOT a phase gate and produces no evaluation numbers. These checks
only assert that the larger world still obeys the frozen world rules: same
vocabulary, same 5-agent fleet with >=2 eligible bidders per task type, loader
reachability, scene-derived priority, and a full deterministic allocation +
execution. The industrial_park golden makespans are covered elsewhere and are
untouched by adding a sibling scene.
"""

from collections import Counter
from pathlib import Path

import pytest

from allocation.allocate import allocate
from core.enums import TaskStatus, TaskType
from core.mission_state import MissionState
from execution.executor import SimExecutor, Termination
from scenarios.compiler import AREA_RECON_PRIORITY
from scenarios.fixture import eligible_bidder_counts, load_reference_fixture

_FIXTURE = Path(__file__).resolve().parents[1] / "scenarios" / "response_district_fixture.yaml"


@pytest.fixture(scope="module")
def loaded():
    return load_reference_fixture(_FIXTURE)


def test_fixture_shape(loaded):
    g = loaded.graph
    assert len(g) == 18
    assert len(g.edges) == 5
    assert len(g.ids_with_status(TaskStatus.READY)) == 13
    assert len(g.ids_with_status(TaskStatus.PENDING)) == 5
    ready_types = Counter(g[tid].task_type for tid in g.ids_with_status(TaskStatus.READY))
    assert ready_types == Counter({TaskType.AREA_RECON: 8, TaskType.GROUND_INSPECTION: 5})


def test_graph_is_well_formed(loaded):
    g = loaded.graph
    ids = [t.task_id for t in g.tasks]
    assert len(ids) == len(set(ids))
    assert g.reference_errors() == []
    assert not g.has_cycle()
    assert len(g.topological_order()) == 18
    for t in g.tasks:
        assert t.target in loaded.scene.zones or t.target in loaded.scene.incidents


def test_every_task_type_has_at_least_two_bidders(loaded):
    counts = eligible_bidder_counts(loaded.scene)
    assert counts == {
        TaskType.AREA_RECON: 3,
        TaskType.GROUND_INSPECTION: 2,
        TaskType.GROUND_SUPPRESSION: 2,
    }


def test_fleet_is_three_uav_two_ugv(loaded):
    kinds = Counter(a.platform_kind.value for a in loaded.scene.fleet)
    assert kinds == Counter({"UAV": 3, "UGV": 2})
    assert len(loaded.scene.fleet) == 5


def test_loader_reachability_holds(loaded):
    assert loaded.scene.reachability_errors(loaded.ugv_target_nodes()) == []


def test_priority_is_scene_derived(loaded):
    g = loaded.graph
    wanted = {
        "FIRE_SITE_1": 10,
        "FIRE_SITE_2": 9,
        "FIRE_SITE_3": 8,
        "FIRE_SITE_4": 7,
        "FIRE_SITE_5": 5,
    }
    for iid, want in wanted.items():
        for tt in ("GROUND_INSPECTION", "GROUND_SUPPRESSION"):
            assert g[f"{tt}__{iid}"].priority == want
    for zid in ("ZONE_A", "ZONE_B", "ZONE_C", "ZONE_D", "ZONE_E", "ZONE_F", "ZONE_G", "ZONE_H"):
        assert g[f"AREA_RECON__{zid}"].priority == AREA_RECON_PRIORITY


def test_deterministic_allocation_assigns_every_task_and_uses_every_agent(loaded):
    def _plan():
        state = MissionState(
            graph=loaded.graph.clone(),
            agents={a.agent_id: a for a in loaded.scene.fleet},
        )
        return allocate(state, loaded.scene)

    first = _plan()
    assert first.allocation_success
    assert not first.capability_violations
    assert not first.precedence_violations
    assert set(first.assignments) == {t.task_id for t in loaded.graph.tasks}
    # heterogeneous: every UAV and every UGV carries work
    assert {"U1", "U2", "U3", "G1", "G2"} <= set(first.assignments.values())

    second = _plan()
    assert second.assignments == first.assignments
    assert second.estimated_makespan == first.estimated_makespan


def test_execution_completes_without_violations(loaded):
    state = MissionState(
        graph=loaded.graph.clone(),
        agents={a.agent_id: a for a in loaded.scene.fleet},
    )
    result = SimExecutor(state, loaded.scene).run()
    assert result.termination is Termination.COMPLETED
    assert not result.capability_violations
    assert not result.precedence_violations
