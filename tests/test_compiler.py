"""Unit tests for the deterministic task compiler (RESEARCH_CONTRACT.md §7)."""

from pathlib import Path

import pytest

from core.enums import Capability, PlatformKind, TaskType
from scenarios.compiler import compile_task, task_id_for
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
    t = compile_task(scene, TaskType.HAZARD_MARKER_DEPLOY, "FIRE_SITE_2", priority=5)
    node = scene.incidents["FIRE_SITE_2"].access_node
    assert t.position == scene.route_graph.position(node)
    assert t.required_capabilities == frozenset(
        {Capability.GROUND_MOBILITY, Capability.MARKER_DISPENSER}
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


def test_task_id_helper_matches_compiled_id(scene):
    t = compile_task(scene, TaskType.GROUND_INSPECTION, "FIRE_SITE_1", priority=8)
    assert t.task_id == task_id_for(TaskType.GROUND_INSPECTION, "FIRE_SITE_1")
