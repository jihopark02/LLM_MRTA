"""P1 completion gate (RESEARCH_CONTRACT.md §15 "P1 완료 게이트", §3 fixed shape).

Every assertion here maps to a numbered gate item. All must pass before P1 is
declared complete.
"""

import pytest

from core.enums import TaskStatus, TaskType
from scenarios.fixture import eligible_bidder_counts, load_reference_fixture


@pytest.fixture(scope="module")
def loaded():
    # Gate item 2: scene + reference fixture load without error.
    return load_reference_fixture()


def test_gate3_fixture_matches_fixed_shape(loaded):
    g = loaded.graph
    assert len(g) == 12
    assert len(g.edges) == 6
    assert len(g.ids_with_status(TaskStatus.READY)) == 6
    assert len(g.ids_with_status(TaskStatus.PENDING)) == 6


def test_gate3_frontier_composition(loaded):
    g = loaded.graph
    ready_types = sorted(g[tid].task_type for tid in g.ids_with_status(TaskStatus.READY))
    assert ready_types == [
        TaskType.AREA_RECON,
        TaskType.AREA_RECON,
        TaskType.AREA_RECON,
        TaskType.AREA_RECON,
        TaskType.THERMAL_RECON,
        TaskType.THERMAL_RECON,
    ]


def test_gate4_all_task_ids_unique(loaded):
    ids = [t.task_id for t in loaded.graph.tasks]
    assert len(ids) == len(set(ids))


def test_gate4_all_targets_reference_existing_area_or_incident(loaded):
    scene = loaded.scene
    for t in loaded.graph.tasks:
        assert t.target in scene.zones or t.target in scene.incidents


def test_gate4_edges_reference_existing_tasks_and_no_self_loop(loaded):
    assert loaded.graph.reference_errors() == []


def test_gate4_graph_is_acyclic(loaded):
    assert not loaded.graph.has_cycle()
    # topological_order raises on a cycle; here it must succeed over all 12 tasks.
    assert len(loaded.graph.topological_order()) == 12


def test_gate5_all_ugv_task_access_nodes_reachable(loaded):
    errors = loaded.scene.reachability_errors(loaded.ugv_target_nodes())
    assert errors == []


def test_eligible_bidder_counts_are_at_least_two(loaded):
    counts = eligible_bidder_counts(loaded.scene)
    assert counts == {
        TaskType.AREA_RECON: 2,
        TaskType.THERMAL_RECON: 4,
        TaskType.SUPPRESSANT_DROP: 2,
        TaskType.GROUND_INSPECTION: 2,
        TaskType.HAZARD_MARKER_DEPLOY: 2,
    }
    assert all(c >= 2 for c in counts.values())
