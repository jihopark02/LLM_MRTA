"""Whole-graph invariants (RESEARCH_CONTRACT.md §9 #4-#12) + §14 result record."""

from pathlib import Path

import pytest
import yaml

from validator.candidate import MissionCandidate
from validator.errors import ErrorCode
from validator.hashing import VALIDATOR_VERSION
from validator.validate import validate_candidate

SCEN = Path(__file__).parents[1] / "scenarios"


@pytest.fixture(scope="module")
def scene():
    from scenarios.scene import load_scene

    return load_scene(SCEN / "industrial_park.yaml")


def reference_raw() -> dict:
    fx = yaml.safe_load((SCEN / "reference_fixture.yaml").read_text())
    return {
        "tasks": [
            {"task_type": t["type"], "target": t["target"], "priority": t["priority"]}
            for t in fx["tasks"]
        ],
        "edges": [list(e) for e in fx["edges"]],
    }


def validate_raw(raw: dict, scene) -> "object":
    cand, schema_errors = MissionCandidate.from_raw(raw)
    assert schema_errors == [], schema_errors
    return validate_candidate(cand, scene)


def codes(result):
    return result.error_codes


def test_reference_family_a_candidate_is_accepted(scene):
    result = validate_raw(reference_raw(), scene)
    assert result.accepted, result.errors
    assert result.errors == ()
    assert result.validator_version == VALIDATOR_VERSION
    assert len(result.graph_hash) == 64 and len(result.scene_hash) == 64


def test_same_candidate_same_hash_and_verdict(scene):
    a = validate_raw(reference_raw(), scene)
    b = validate_raw(reference_raw(), scene)
    assert a.graph_hash == b.graph_hash
    assert a.scene_hash == b.scene_hash
    assert a.accepted == b.accepted


def test_graph_hash_ignores_task_order_but_not_priority(scene):
    raw = reference_raw()
    reordered = {"tasks": list(reversed(raw["tasks"])), "edges": raw["edges"]}
    assert validate_raw(raw, scene).graph_hash == validate_raw(reordered, scene).graph_hash

    bumped = {
        "tasks": [{**t, "priority": t["priority"] + 1} for t in raw["tasks"]],
        "edges": raw["edges"],
    }
    assert validate_raw(raw, scene).graph_hash != validate_raw(bumped, scene).graph_hash


def test_unexpected_top_level_or_task_key_is_schema_error(scene):
    _, e1 = MissionCandidate.from_raw({"tasks": [], "edges": [], "notes": "x"})
    assert [x.code for x in e1] == [ErrorCode.E_SCHEMA]
    task_with_extra = {
        "task_type": "AREA_RECON",
        "target": "ZONE_A",
        "priority": 1,
        "assigned_agent": "S1",
    }
    _, e2 = MissionCandidate.from_raw({"tasks": [task_with_extra], "edges": []})
    assert ErrorCode.E_SCHEMA in [x.code for x in e2]


def test_unknown_target_is_flagged(scene):
    raw = {"tasks": [{"task_type": "AREA_RECON", "target": "ZONE_Z", "priority": 1}], "edges": []}
    assert ErrorCode.E_UNKNOWN_REF in codes(validate_raw(raw, scene))


def test_cycle_is_flagged(scene):
    raw = {
        "tasks": [
            {"task_type": "THERMAL_RECON", "target": "FIRE_SITE_1", "priority": 9},
            {"task_type": "SUPPRESSANT_DROP", "target": "FIRE_SITE_1", "priority": 9},
        ],
        "edges": [
            ["THERMAL_RECON:FIRE_SITE_1", "SUPPRESSANT_DROP:FIRE_SITE_1"],
            ["SUPPRESSANT_DROP:FIRE_SITE_1", "THERMAL_RECON:FIRE_SITE_1"],
        ],
    }
    assert ErrorCode.E_CYCLE in codes(validate_raw(raw, scene))


def test_missing_workflow_predecessor_is_flagged(scene):
    # SUPPRESSANT_DROP without its THERMAL_RECON predecessor (§4 conditional chain).
    raw = {
        "tasks": [{"task_type": "SUPPRESSANT_DROP", "target": "FIRE_SITE_1", "priority": 9}],
        "edges": [],
    }
    assert ErrorCode.E_WORKFLOW in codes(validate_raw(raw, scene))


def test_partial_aerial_only_graph_is_accepted(scene):
    # THERMAL_RECON alone is a valid partial graph (Family B): chain head, no predecessor.
    raw = {
        "tasks": [
            {"task_type": "AREA_RECON", "target": "ZONE_A", "priority": 3},
            {"task_type": "THERMAL_RECON", "target": "FIRE_SITE_1", "priority": 9},
        ],
        "edges": [],
    }
    assert validate_raw(raw, scene).accepted


def test_chain_head_with_predecessor_is_flagged(scene):
    raw = {
        "tasks": [
            {"task_type": "AREA_RECON", "target": "ZONE_A", "priority": 3},
            {"task_type": "THERMAL_RECON", "target": "FIRE_SITE_1", "priority": 9},
        ],
        "edges": [["AREA_RECON:ZONE_A", "THERMAL_RECON:FIRE_SITE_1"]],
    }
    assert ErrorCode.E_WORKFLOW in codes(validate_raw(raw, scene))


def test_cross_incident_edge_is_flagged(scene):
    raw = {
        "tasks": [
            {"task_type": "THERMAL_RECON", "target": "FIRE_SITE_1", "priority": 9},
            {"task_type": "SUPPRESSANT_DROP", "target": "FIRE_SITE_2", "priority": 7},
        ],
        "edges": [["THERMAL_RECON:FIRE_SITE_1", "SUPPRESSANT_DROP:FIRE_SITE_2"]],
    }
    got = codes(validate_raw(raw, scene))
    assert ErrorCode.E_CROSS_INCIDENT in got
    assert ErrorCode.E_WORKFLOW in got  # SUPPRESSANT_DROP:F2 lacks THERMAL_RECON:F2


def test_unreachable_ugv_task_is_flagged(tmp_path):
    from scenarios.scene import load_scene

    # A scene where the incident access node is isolated from the UGV start node.
    bad = tmp_path / "iso.yaml"
    bad.write_text(
        "scene_id: iso\n"
        "zones: {ZONE_A: {name: A, recon_waypoint: [0, 0]}}\n"
        "incidents: {F1: {zone: ZONE_A, priority: 1, position: [1, 1], access_node: ISO,"
        " status: RESPONSE_REQUIRED}}\n"
        "route_graph: {nodes: {DEPOT: [0, 0], ISO: [9, 9]}, lanes: []}\n"
        "fleet:\n"
        "  - {agent_id: G1, platform_kind: UGV,"
        " capabilities: [GROUND_MOBILITY, MARKER_DISPENSER], access_node: DEPOT, speed: 3}\n"
        "  - {agent_id: R1, platform_kind: UAV,"
        " capabilities: [THERMAL_SENSOR, SUPPRESSANT_PAYLOAD], position: [0, 0], speed: 7}\n"
    )
    scene = load_scene(bad)
    raw = {
        "tasks": [{"task_type": "GROUND_INSPECTION", "target": "F1", "priority": 1}],
        "edges": [],
    }
    cand, errs = MissionCandidate.from_raw(raw)
    assert errs == []
    result = validate_candidate(cand, scene)
    assert ErrorCode.E_UNREACHABLE in result.error_codes


def test_infeasible_when_no_agent_has_capability(tmp_path):
    from scenarios.scene import load_scene

    bad = tmp_path / "nocap.yaml"
    bad.write_text(
        "scene_id: nocap\n"
        "zones: {ZONE_A: {name: A, recon_waypoint: [0, 0]}}\n"
        "incidents: {F1: {zone: ZONE_A, priority: 1, position: [1, 1], access_node: N0,"
        " status: RESPONSE_REQUIRED}}\n"
        "route_graph: {nodes: {N0: [0, 0]}, lanes: []}\n"
        "fleet:\n"
        "  - {agent_id: S1, platform_kind: UAV, capabilities: [AERIAL_RECON],"
        " position: [0, 0], speed: 8}\n"
    )
    scene = load_scene(bad)
    raw = {
        "tasks": [{"task_type": "SUPPRESSANT_DROP", "target": "F1", "priority": 1}],
        "edges": [],
    }
    cand, _ = MissionCandidate.from_raw(raw)
    assert ErrorCode.E_INFEASIBLE in validate_candidate(cand, scene).error_codes
