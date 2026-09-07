"""P8.5a gate: the deterministic DAG render spec (§18.14, D-043/D-044).

The determinism gate is the spec, never the image: a matplotlib ``Figure`` has
no equality and its bytes move with the matplotlib version, fonts and backend
(D-044). Everything here is checked on the structured value.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from core.enums import PlatformKind, TaskStatus, TaskType
from demo.visualization import (
    MIXED_MARKER,
    STATUS_COLORS,
    TYPE_LABELS,
    UAV_MARKER,
    UGV_MARKER,
    dag_render_spec,
)
from interaction.ground import build_chain_patch
from interaction.scene_mut import register_incident
from interaction.session import fresh_session_state
from scenarios.fixture import load_reference_fixture
from scenarios.scene import load_scene
from validator.hashing import pre_state_hash, scene_hash
from validator.patch_apply import apply_patch

SCENARIOS = Path(__file__).parents[1] / "scenarios"


@pytest.fixture
def scene():
    return load_scene(SCENARIOS / "industrial_park.yaml")


@pytest.fixture
def graph():
    return load_reference_fixture().graph


# -- the spec must not need matplotlib (D-044 degrade path) --------------


def test_building_a_spec_never_imports_matplotlib():
    # In a subprocess, because another test in the session may already have
    # imported matplotlib — an in-process check would silently degrade to a
    # skip. This is what lets the console start without the viz extra (D-044).
    probe = (
        "import sys;"
        "import demo.visualization as v;"
        "from scenarios.fixture import load_reference_fixture;"
        "v.dag_render_spec(load_reference_fixture().graph);"
        "hit=[n for n in sys.modules if n=='matplotlib' or n.startswith('matplotlib.')];"
        "print('LEAK' if hit else 'CLEAN')"
    )
    done = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
        check=True,
    )
    assert done.stdout.strip() == "CLEAN", done.stdout


# -- colour / label tables cover the enums ------------------------------


def test_every_task_status_has_a_colour():
    # Iterating the enum, not a hand-written list: adding a TaskStatus member
    # must break here rather than at draw time (D-044).
    assert set(STATUS_COLORS) == set(TaskStatus)
    assert len(set(STATUS_COLORS.values())) == len(TaskStatus), "colours must be distinct"
    assert TaskStatus.CANCELLED in STATUS_COLORS


def test_every_task_type_has_a_label():
    assert set(TYPE_LABELS) == set(TaskType)
    assert len(set(TYPE_LABELS.values())) == len(TaskType)


# -- spec agrees with the graph -----------------------------------------


def test_spec_nodes_are_exactly_the_graph_tasks(graph):
    spec = dag_render_spec(graph)
    assert spec.task_ids == {task.task_id for task in graph.tasks}
    assert len(spec.nodes) == len(graph)


def test_spec_edges_are_exactly_the_graph_edges(graph):
    spec = dag_render_spec(graph)
    assert spec.edge_keys == graph.edges
    assert len(spec.edges) == len(graph.edges)


def test_every_node_carries_its_status_colour_and_platform_marker(graph):
    spec = dag_render_spec(graph)
    for node in spec.nodes:
        task = graph[node.task_id]
        assert node.status is task.status
        assert node.color == STATUS_COLORS[task.status]
        assert node.label == TYPE_LABELS[task.task_type]
        assert node.target == task.target
        expected = {
            frozenset({PlatformKind.UAV}): UAV_MARKER,
            frozenset({PlatformKind.UGV}): UGV_MARKER,
        }.get(task.eligible_platforms, MIXED_MARKER)
        assert node.marker == expected


def test_a_status_change_moves_only_the_colour(graph):
    before = {node.task_id: node for node in dag_render_spec(graph).nodes}
    target = sorted(graph.ids_with_status(TaskStatus.READY))[0]
    graph[target].status = TaskStatus.RUNNING

    after = {node.task_id: node for node in dag_render_spec(graph).nodes}
    assert after[target].color == STATUS_COLORS[TaskStatus.RUNNING]
    assert (after[target].x, after[target].y) == (before[target].x, before[target].y)
    assert {k: (v.x, v.y) for k, v in after.items()} == {
        k: (v.x, v.y) for k, v in before.items()
    }


# -- layout ---------------------------------------------------------------


def test_no_two_nodes_share_a_cell(graph):
    spec = dag_render_spec(graph)
    coordinates = [(node.x, node.y) for node in spec.nodes]
    assert len(set(coordinates)) == len(coordinates)


def test_rows_are_targets_and_columns_are_workflow_steps(graph):
    spec = dag_render_spec(graph)
    rows = {node.target: node.y for node in spec.nodes}
    # one row per target, and every node of a target sits on it
    for node in spec.nodes:
        assert node.y == rows[node.target]
    # zone recon rows come before incident rows, and each chain advances right
    assert spec.row_labels[:4] == ("ZONE_A", "ZONE_B", "ZONE_C", "ZONE_D")
    assert spec.row_labels[4:] == ("FIRE_SITE_1", "FIRE_SITE_2")
    chain = [n for n in spec.nodes if n.target == "FIRE_SITE_1"]
    assert sorted(n.x for n in chain) == [0.0, 1.0, 2.0, 3.0]


def test_incident_rows_sort_naturally_not_lexicographically(scene):
    # FIRE_SITE_10 must not sort ahead of FIRE_SITE_2 and make the figure lie.
    for _ in range(9):
        scene, _ = register_incident(scene, "ZONE_A")
    assert "FIRE_SITE_10" in scene.incidents

    from core.mission_state import MissionState
    from scenarios.compiler import compile_reference_graph

    specs = [(TaskType.THERMAL_RECON, iid) for iid in scene.incidents]
    built = compile_reference_graph(scene, specs, [])
    spec = dag_render_spec(MissionState(built, {}).graph)
    assert spec.row_labels[-3:] == ("FIRE_SITE_9", "FIRE_SITE_10", "FIRE_SITE_11")


# -- determinism ----------------------------------------------------------


def test_the_same_graph_always_yields_the_same_spec(graph):
    assert dag_render_spec(graph) == dag_render_spec(graph)


def test_the_spec_does_not_depend_on_task_insertion_order(graph):
    from core.task_graph import TaskGraph

    shuffled = TaskGraph()
    for task in sorted(graph.tasks, key=lambda t: t.task_id, reverse=True):
        shuffled.add_task(task)
    for pred, succ in sorted(graph.edges, reverse=True):
        shuffled.add_edge(pred, succ)

    assert dag_render_spec(shuffled) == dag_render_spec(graph)


def test_gids_are_the_task_and_edge_identities(graph):
    spec = dag_render_spec(graph)
    assert {node.gid for node in spec.nodes} == {task.task_id for task in graph.tasks}
    assert {edge.gid for edge in spec.edges} == {
        f"{pred}->{succ}" for pred, succ in graph.edges
    }


# -- purity and online updates --------------------------------------------


def test_rendering_leaves_the_session_state_untouched(scene, graph):
    state = fresh_session_state(graph, scene)
    before = (pre_state_hash(state), scene_hash(scene))

    dag_render_spec(state.graph)

    assert (pre_state_hash(state), scene_hash(scene)) == before


def test_an_online_update_adds_a_row_and_its_tasks_to_the_next_spec(scene, graph):
    state = fresh_session_state(graph, scene)
    before = dag_render_spec(state.graph)

    updated_scene, incident_id = register_incident(scene, "ZONE_A")
    plan = build_chain_patch(state.graph, incident_id, "GROUND_SUPPRESSION")
    committed, result = apply_patch(state, plan.patch, updated_scene)
    assert result.accepted

    after = dag_render_spec(committed.graph)

    # the new incident becomes its own row, and its whole chain is drawn
    assert incident_id not in before.row_labels
    assert incident_id in after.row_labels
    assert after.task_ids - before.task_ids == set(result.added_tasks)
    assert after.edge_keys == committed.graph.edges
    assert len(after.nodes) == len(before.nodes) + len(result.added_tasks)
