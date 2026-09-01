"""Unit tests for the semantic scene loader (RESEARCH_CONTRACT.md §3, §5, §8)."""

from pathlib import Path

import pytest

from core.enums import Capability, PlatformKind
from scenarios.scene import load_scene

SCENE_PATH = Path(__file__).parents[1] / "scenarios" / "industrial_park.yaml"


@pytest.fixture
def scene():
    return load_scene(SCENE_PATH)


def test_scene_loads_expected_vocabulary(scene):
    assert set(scene.zones) == {"ZONE_A", "ZONE_B", "ZONE_C", "ZONE_D"}
    assert set(scene.incidents) == {"FIRE_SITE_1", "FIRE_SITE_2"}
    assert {a.agent_id for a in scene.fleet} == {"S1", "S2", "R1", "R2", "G1", "G2"}


def test_fleet_is_two_two_two(scene):
    by_kind: dict[PlatformKind, int] = {}
    for a in scene.fleet:
        by_kind[a.platform_kind] = by_kind.get(a.platform_kind, 0) + 1
    assert by_kind == {PlatformKind.UAV: 4, PlatformKind.UGV: 2}


def test_ugv_position_is_taken_from_its_route_node(scene):
    g1 = next(a for a in scene.fleet if a.agent_id == "G1")
    assert scene.agent_access_nodes["G1"] == "R_DEPOT"
    assert g1.position == scene.route_graph.position("R_DEPOT")
    assert g1.initial_position == g1.position


def test_incident_access_nodes_are_in_route_graph(scene):
    for incident in scene.incidents.values():
        assert incident.access_node in scene.route_graph


def test_eligible_agents_filters_by_platform_and_capability(scene):
    responders = scene.eligible_agents(
        frozenset({Capability.SUPPRESSANT_PAYLOAD}), frozenset({PlatformKind.UAV})
    )
    assert {a.agent_id for a in responders} == {"R1", "R2"}


def test_incident_referencing_unknown_zone_is_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "scene_id: bad\n"
        "zones: {ZONE_A: {name: A, recon_waypoint: [0, 0]}}\n"
        "incidents: {F1: {zone: ZONE_X, priority: 1, position: [1, 1], access_node: N0}}\n"
        "route_graph: {nodes: {N0: [0, 0]}, lanes: []}\n"
        "fleet: []\n"
    )
    with pytest.raises(ValueError, match="unknown zone"):
        load_scene(bad)
