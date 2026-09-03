"""P8.1c: operator-reported incident registration (§18.1, §18.8, §18.10, D-027).

Two things must hold: the generated incident is a fully valid scene member that
the Validator and the compiler accept, and the call is a transaction — the
original Scene comes out byte-identical by hash and by field.
"""

from pathlib import Path

import pytest

from core.enums import IncidentStatus, TaskType
from interaction.scene_mut import (
    REPORTED_INCIDENT_PRIORITY,
    next_incident_id,
    register_incident,
)
from scenarios.compiler import derive_priority
from scenarios.scene import load_scene
from validator.candidate import MissionCandidate
from validator.hashing import scene_hash
from validator.validate import validate_candidate

SCENE = Path(__file__).parents[1] / "scenarios" / "industrial_park.yaml"


@pytest.fixture
def scene():
    return load_scene(SCENE)


# -- id generation (§18.10) -------------------------------------------


def test_next_id_is_highest_plus_one():
    assert next_incident_id(["FIRE_SITE_1", "FIRE_SITE_2"]) == "FIRE_SITE_3"


def test_next_id_does_not_reuse_a_gap():
    # FIRE_SITE_2 was removed; the counter must not hand it out again.
    assert next_incident_id(["FIRE_SITE_1", "FIRE_SITE_3"]) == "FIRE_SITE_4"


def test_next_id_starts_at_one_when_nothing_is_registered():
    assert next_incident_id([]) == "FIRE_SITE_1"


@pytest.mark.parametrize(
    "malformed",
    ["FIRE_SITE_0", "FIRE_SITE_02", "FIRE_SITE_", "FIRE_SITE_1x", "fire_site_9", "F9"],
)
def test_malformed_ids_do_not_skew_the_counter(malformed):
    assert next_incident_id(["FIRE_SITE_1", malformed]) == "FIRE_SITE_2"


@pytest.mark.parametrize(
    "existing",
    [
        [],
        ["FIRE_SITE_1"],
        ["FIRE_SITE_1", "FIRE_SITE_2", "FIRE_SITE_10"],
        ["FIRE_SITE_0", "FIRE_SITE_02", "FIRE_SITE_1x"],
        ["FIRE_SITE_99", "weird", "FIRE_SITE_"],
    ],
)
def test_generated_id_never_collides(existing):
    # The property that matters: uniqueness against every existing id, however
    # malformed, not just against the ones the pattern counts.
    assert next_incident_id(existing) not in set(existing)


# -- the registered incident (§18.10) ---------------------------------


def test_registered_incident_uses_the_zone_response_point(scene):
    new_scene, iid = register_incident(scene, "ZONE_C")
    zone = scene.zones["ZONE_C"]
    inc = new_scene.incidents[iid]

    assert iid == "FIRE_SITE_3"  # scene already has 1 and 2
    assert inc.zone == "ZONE_C"
    assert inc.position == zone.reported_incident_position
    assert inc.access_node == zone.reported_incident_access_node
    assert inc.status is IncidentStatus.RESPONSE_REQUIRED


def test_registered_incident_priority_is_the_fixed_constant(scene):
    new_scene, iid = register_incident(scene, "ZONE_A")
    assert new_scene.incidents[iid].priority == REPORTED_INCIDENT_PRIORITY == 7
    # and the compiler derives the same number for its tasks
    assert derive_priority(new_scene, TaskType.THERMAL_RECON, iid) == 7


def test_two_reports_in_the_same_zone_are_both_registered(scene):
    # §18.4: multiple incidents per zone are allowed.
    s1, first = register_incident(scene, "ZONE_A")
    s2, second = register_incident(s1, "ZONE_A")
    assert [first, second] == ["FIRE_SITE_3", "FIRE_SITE_4"]
    assert s2.incidents[first].zone == s2.incidents[second].zone == "ZONE_A"
    assert len(s2.incidents) == 4


def test_unknown_zone_is_rejected(scene):
    with pytest.raises(ValueError, match="unknown zone"):
        register_incident(scene, "ZONE_Z")


# -- transaction: the original scene is untouched (§18.8) -------------


def test_failed_registration_leaves_the_scene_untouched(scene):
    before_hash = scene_hash(scene)
    before_ids = sorted(scene.incidents)
    with pytest.raises(ValueError):
        register_incident(scene, "NOPE")
    assert scene_hash(scene) == before_hash
    assert sorted(scene.incidents) == before_ids


def test_successful_registration_leaves_the_original_scene_untouched(scene):
    before_hash = scene_hash(scene)
    before_ids = sorted(scene.incidents)

    new_scene, iid = register_incident(scene, "ZONE_B")

    assert scene_hash(scene) == before_hash
    assert sorted(scene.incidents) == before_ids
    assert iid not in scene.incidents
    assert scene.incidents is not new_scene.incidents
    assert scene_hash(new_scene) != before_hash


def test_shared_fields_are_shared_but_never_mutated(scene):
    # §18.8: zones / route_graph / fleet may be shared structurally; only the
    # incidents dict is rebuilt.
    new_scene, _ = register_incident(scene, "ZONE_D")
    assert new_scene.zones is scene.zones
    assert new_scene.route_graph is scene.route_graph
    assert new_scene.fleet is scene.fleet
    assert new_scene.agent_access_nodes is scene.agent_access_nodes
    assert new_scene.scene_id == scene.scene_id


def test_registration_is_deterministic(scene):
    a, ia = register_incident(scene, "ZONE_C")
    b, ib = register_incident(scene, "ZONE_C")
    assert ia == ib
    assert scene_hash(a) == scene_hash(b)


# -- the new incident is a first-class scene member -------------------


def test_a_full_chain_on_the_new_incident_passes_the_validator(scene):
    new_scene, iid = register_incident(scene, "ZONE_A")
    chain = ["THERMAL_RECON", "SUPPRESSANT_DROP", "GROUND_INSPECTION", "GROUND_SUPPRESSION"]
    cand, errors = MissionCandidate.from_raw(
        {
            "tasks": [{"task_type": t, "target": iid} for t in chain],
            "edges": [[f"{a}:{iid}", f"{b}:{iid}"] for a, b in zip(chain, chain[1:], strict=False)],
        }
    )
    assert errors == []
    result = validate_candidate(cand, new_scene)
    assert result.accepted, result.errors


@pytest.mark.parametrize("zone_id", ["ZONE_A", "ZONE_B", "ZONE_C", "ZONE_D"])
def test_ugv_tasks_on_a_report_in_any_zone_are_reachable(zone_id, scene):
    # Scene load guarantees every zone's response node is UGV-reachable, so a
    # GROUND_* task on a report in any zone must clear invariant #12.
    new_scene, iid = register_incident(scene, zone_id)
    cand, errors = MissionCandidate.from_raw(
        {
            "tasks": [
                {"task_type": "THERMAL_RECON", "target": iid},
                {"task_type": "SUPPRESSANT_DROP", "target": iid},
                {"task_type": "GROUND_INSPECTION", "target": iid},
            ],
            "edges": [
                [f"THERMAL_RECON:{iid}", f"SUPPRESSANT_DROP:{iid}"],
                [f"SUPPRESSANT_DROP:{iid}", f"GROUND_INSPECTION:{iid}"],
            ],
        }
    )
    assert errors == []
    assert validate_candidate(cand, new_scene).accepted


def test_existing_incidents_still_validate_after_a_registration(scene):
    new_scene, _ = register_incident(scene, "ZONE_C")
    cand, errors = MissionCandidate.from_raw(
        {"tasks": [{"task_type": "THERMAL_RECON", "target": "FIRE_SITE_1"}], "edges": []}
    )
    assert errors == []
    assert validate_candidate(cand, new_scene).accepted
