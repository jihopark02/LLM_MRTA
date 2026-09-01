"""Platform-aware travel cost (RESEARCH_CONTRACT.md §8) — P3 gate: UGV uses route distance."""

import math
from pathlib import Path

import pytest

from core.enums import TaskType
from scenarios.compiler import compile_task
from scenarios.scene import load_scene

SCENE = Path(__file__).parents[1] / "scenarios" / "industrial_park.yaml"


@pytest.fixture(scope="module")
def scene():
    return load_scene(SCENE)


def agent(scene, agent_id):
    return next(a for a in scene.fleet if a.agent_id == agent_id)


def test_uav_leg_is_euclidean_over_speed(scene):
    from allocation.travel import leg_time, start_ref

    s1 = agent(scene, "S1")
    task = compile_task(scene, TaskType.AREA_RECON, "ZONE_A", 4)
    expected = math.dist(s1.position, task.position) / s1.speed
    assert leg_time(s1, start_ref(s1, scene), task, scene) == pytest.approx(expected)


def test_ugv_leg_uses_route_distance_not_euclidean(scene):
    from allocation.travel import leg_time, start_ref

    g1 = agent(scene, "G1")  # starts at R_DEPOT
    task = compile_task(scene, TaskType.GROUND_INSPECTION, "FIRE_SITE_1", 8)
    node = scene.incidents["FIRE_SITE_1"].access_node

    route = scene.route_graph.shortest_path_distance("R_DEPOT", node) / g1.speed
    euclid = math.dist(scene.route_graph.position("R_DEPOT"), task.position) / g1.speed

    got = leg_time(g1, start_ref(g1, scene), task, scene)
    assert got == pytest.approx(route)
    assert got > euclid  # the route graph is not a straight line here


def test_ugv_start_ref_is_its_access_node(scene):
    from allocation.travel import start_ref

    assert start_ref(agent(scene, "G2"), scene) == "R_C"


def test_ugv_task_ref_is_incident_access_node(scene):
    from allocation.travel import task_ref

    g1 = agent(scene, "G1")
    task = compile_task(scene, TaskType.GROUND_SUPPRESSION, "FIRE_SITE_2", 5)
    assert task_ref(g1, task, scene) == "R_D"


def test_chained_ugv_legs_advance_the_node(scene):
    from allocation.travel import leg_time, start_ref, task_ref

    g1 = agent(scene, "G1")
    gi = compile_task(scene, TaskType.GROUND_INSPECTION, "FIRE_SITE_1", 8)
    gs = compile_task(scene, TaskType.GROUND_SUPPRESSION, "FIRE_SITE_1", 6)

    ref = start_ref(g1, scene)
    leg1 = leg_time(g1, ref, gi, scene)
    ref = task_ref(g1, gi, scene)
    leg2 = leg_time(g1, ref, gs, scene)  # from R_B to R_B == 0
    assert leg1 > 0
    assert leg2 == pytest.approx(0.0)
