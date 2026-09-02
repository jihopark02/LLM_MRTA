"""Unit tests for the semantic scene loader (RESEARCH_CONTRACT.md §3, §5, §8)."""

from pathlib import Path

import pytest

from core.enums import Capability, IncidentStatus, PlatformKind
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


def test_incidents_carry_response_required_status(scene):
    assert all(
        i.status is IncidentStatus.RESPONSE_REQUIRED for i in scene.incidents.values()
    )


def _minimal_scene_yaml(incident_line: str, fleet_line: str = "fleet: []") -> str:
    return (
        "scene_id: t\n"
        "zones: {ZONE_A: {name: A, recon_waypoint: [0, 0]}}\n"
        f"incidents: {{{incident_line}}}\n"
        "route_graph: {nodes: {N0: [0, 0], N1: [3, 4]}, lanes: [[N0, N1]]}\n"
        f"{fleet_line}\n"
    )


def test_invalid_incident_status_is_rejected(tmp_path):
    bad = tmp_path / "s.yaml"
    bad.write_text(
        _minimal_scene_yaml(
            "F1: {zone: ZONE_A, priority: 1, position: [1, 1], access_node: N0, status: ON_FIRE}"
        )
    )
    with pytest.raises(ValueError):
        load_scene(bad)


@pytest.mark.parametrize("bad", ["0", "11", "true", '"9"'])
def test_incident_priority_out_of_1_to_10_or_non_int_is_rejected(tmp_path, bad):
    # D-022: the scene is the source of truth for priority; the compiler trusts
    # it, so the scene loader must reject anything that is not an int in 1..10 —
    # no int() coercion (bool -> 1, "9" -> 9 must NOT slip through).
    s = tmp_path / "s.yaml"
    s.write_text(
        _minimal_scene_yaml(
            f"F1: {{zone: ZONE_A, priority: {bad}, position: [1, 1], access_node: N0,"
            " status: RESPONSE_REQUIRED}"
        )
    )
    with pytest.raises(ValueError, match="priority"):
        load_scene(s)


def test_incident_access_node_missing_from_route_graph_is_rejected(tmp_path):
    bad = tmp_path / "s.yaml"
    bad.write_text(
        _minimal_scene_yaml(
            "F1: {zone: ZONE_A, priority: 1, position: [1, 1], access_node: GHOST,"
            " status: RESPONSE_REQUIRED}"
        )
    )
    with pytest.raises(ValueError, match="not in route graph"):
        load_scene(bad)


def test_duplicate_agent_id_is_rejected(tmp_path):
    bad = tmp_path / "s.yaml"
    bad.write_text(
        _minimal_scene_yaml(
            "F1: {zone: ZONE_A, priority: 1, position: [1, 1], access_node: N0,"
            " status: RESPONSE_REQUIRED}",
            "fleet:\n"
            "  - {agent_id: S1, platform_kind: UAV, capabilities: [AERIAL_RECON],"
            " position: [0, 0], speed: 5}\n"
            "  - {agent_id: S1, platform_kind: UAV, capabilities: [THERMAL_SENSOR],"
            " position: [0, 0], speed: 5}",
        )
    )
    with pytest.raises(ValueError, match="duplicate agent_id"):
        load_scene(bad)


def test_non_positive_agent_speed_is_rejected(tmp_path):
    bad = tmp_path / "s.yaml"
    bad.write_text(
        _minimal_scene_yaml(
            "F1: {zone: ZONE_A, priority: 1, position: [1, 1], access_node: N0,"
            " status: RESPONSE_REQUIRED}",
            "fleet:\n"
            "  - {agent_id: X1, platform_kind: UAV, capabilities: [AERIAL_RECON],"
            " position: [0, 0], speed: 0}",
        )
    )
    with pytest.raises(ValueError, match="speed"):
        load_scene(bad)


def test_eligible_agents_filters_by_platform_and_capability(scene):
    responders = scene.eligible_agents(
        frozenset({Capability.SUPPRESSANT_PAYLOAD}), frozenset({PlatformKind.UAV})
    )
    assert {a.agent_id for a in responders} == {"R1", "R2"}


def test_incident_referencing_unknown_zone_is_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        _minimal_scene_yaml(
            "F1: {zone: ZONE_X, priority: 1, position: [1, 1], access_node: N0,"
            " status: RESPONSE_REQUIRED}"
        )
    )
    with pytest.raises(ValueError, match="unknown zone"):
        load_scene(bad)
