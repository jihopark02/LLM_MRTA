"""Unit tests for the deterministic task compiler (RESEARCH_CONTRACT.md §7)."""

from pathlib import Path

import pytest

from core.enums import Capability, PlatformKind, TaskStatus, TaskType
from scenarios.compiler import compile_reference_graph, compile_task, task_id_for
from scenarios.scene import load_scene

SCENE_PATH = Path(__file__).parents[1] / "scenarios" / "industrial_park.yaml"


@pytest.fixture
def scene():
    return load_scene(SCENE_PATH)


def test_area_recon_resolves_to_zone_waypoint(scene):
    t = compile_task(scene, TaskType.AREA_RECON, "ZONE_A", priority=4)
    assert t.task_id == "AREA_RECON__ZONE_A"
    assert t.position == scene.zones["ZONE_A"].recon_waypoint
    assert t.eligible_platforms == frozenset({PlatformKind.UAV})
    assert t.required_capabilities == frozenset({Capability.AERIAL_RECON})


def test_thermal_recon_resolves_to_incident_position(scene):
    t = compile_task(scene, TaskType.THERMAL_RECON, "FIRE_SITE_1", priority=9)
    assert t.position == scene.incidents["FIRE_SITE_1"].position


def test_ugv_task_resolves_to_incident_access_node_position(scene):
    t = compile_task(scene, TaskType.GROUND_SUPPRESSION, "FIRE_SITE_2", priority=5)
    node = scene.incidents["FIRE_SITE_2"].access_node
    assert t.position == scene.route_graph.position(node)
    assert t.required_capabilities == frozenset(
        {Capability.GROUND_MOBILITY, Capability.SUPPRESSANT_APPLICATOR}
    )


def test_compile_is_deterministic(scene):
    a = compile_task(scene, TaskType.SUPPRESSANT_DROP, "FIRE_SITE_1", priority=9)
    b = compile_task(scene, TaskType.SUPPRESSANT_DROP, "FIRE_SITE_1", priority=9)
    assert a == b


def test_unknown_target_is_rejected(scene):
    with pytest.raises(ValueError, match="unknown zone"):
        compile_task(scene, TaskType.AREA_RECON, "ZONE_Z", priority=1)
    with pytest.raises(ValueError, match="unknown incident"):
        compile_task(scene, TaskType.THERMAL_RECON, "FIRE_SITE_9", priority=1)


@pytest.mark.parametrize("bad", [0, 11, -3, True, 5.8, "7"])
def test_compile_task_does_not_launder_bad_priority(scene, bad):
    # int(priority) coercion removed (D-008) — Task.__post_init__ rejects it.
    with pytest.raises(ValueError, match="priority"):
        compile_task(scene, TaskType.AREA_RECON, "ZONE_A", priority=bad)


def test_reference_fixture_with_out_of_range_priority_is_rejected(scene, tmp_path):
    fx = tmp_path / "bad_fixture.yaml"
    fx.write_text(
        "fixture_id: bad\nscene: industrial_park\n"
        "tasks:\n  - {type: AREA_RECON, target: ZONE_A, priority: 42}\nedges: []\n"
    )
    from scenarios.fixture import load_reference_fixture

    with pytest.raises(ValueError, match="priority"):
        load_reference_fixture(fx)


def test_task_id_helper_matches_compiled_id(scene):
    t = compile_task(scene, TaskType.GROUND_INSPECTION, "FIRE_SITE_1", priority=8)
    assert t.task_id == task_id_for(TaskType.GROUND_INSPECTION, "FIRE_SITE_1")


# -- compile_reference_graph: trusted-list strictness ----------------------

_TWO_TASKS = [
    (TaskType.THERMAL_RECON, "FIRE_SITE_1", 9),
    (TaskType.SUPPRESSANT_DROP, "FIRE_SITE_1", 9),
]
_GOOD_EDGE = ((TaskType.THERMAL_RECON, "FIRE_SITE_1"), (TaskType.SUPPRESSANT_DROP, "FIRE_SITE_1"))


def test_reference_graph_builds_and_recomputes_frontier(scene):
    g = compile_reference_graph(scene, _TWO_TASKS, [_GOOD_EDGE])
    assert len(g) == 2 and len(g.edges) == 1
    assert g.ids_with_status(TaskStatus.READY) == {"THERMAL_RECON__FIRE_SITE_1"}
    assert g.ids_with_status(TaskStatus.PENDING) == {"SUPPRESSANT_DROP__FIRE_SITE_1"}


def test_reference_graph_rejects_unknown_edge_endpoint(scene):
    bad_edge = (
        (TaskType.THERMAL_RECON, "FIRE_SITE_1"),
        (TaskType.GROUND_INSPECTION, "FIRE_SITE_2"),  # not in the task list
    )
    with pytest.raises(ValueError, match="not a compiled task"):
        compile_reference_graph(scene, _TWO_TASKS, [bad_edge])


def test_reference_graph_rejects_duplicate_edge(scene):
    with pytest.raises(ValueError, match="duplicate edge"):
        compile_reference_graph(scene, _TWO_TASKS, [_GOOD_EDGE, _GOOD_EDGE])
