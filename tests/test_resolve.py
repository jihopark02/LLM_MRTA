"""D-076: deterministic Clause Resolver — Semantic Mission IR against a live world.

Scene: industrial_park (ZONE_A..D, FIRE_SITE_1@ZONE_B [128,108], FIRE_SITE_2@ZONE_D [205,42]).
bbox of recon_waypoints: x[30,200] y[40,180] -> cx=115 cy=110.
"""

from pathlib import Path

import pytest

from interaction.audit import IncidentObservationAudit
from interaction.ground import ClarificationReason, GroundingStatus
from interaction.mission_ir import (
    IncidentSelector,
    ReconClause,
    ResponseClause,
    SemanticMissionIR,
    ZoneSelector,
)
from interaction.resolve import ResolvedMissionIR, resolve_mission_ir
from interaction.session import MissionSession, fresh_session_state
from scenarios.compiler import compile_reference_graph
from scenarios.scene import load_scene

SCENE = Path(__file__).parents[1] / "scenarios" / "industrial_park.yaml"


@pytest.fixture
def scene():
    return load_scene(SCENE)


def sess(scene, **kw):
    return MissionSession("RES", scene, **kw)


def _recon_ir(**zone_kw):
    return SemanticMissionIR(recon=(ReconClause(zones=ZoneSelector(**zone_kw)),))


def _resolved(ir, session) -> ResolvedMissionIR:
    out = resolve_mission_ir(ir, session)
    assert isinstance(out, ResolvedMissionIR), out
    return out


# -- zone selectors --------------------------------------------------


def test_explicit_zones(scene):
    out = _resolved(_recon_ir(explicit=("A 구역", "Tank Farm")), sess(scene))
    assert out.recon[0].zone_ids == ("ZONE_A", "ZONE_D")


def test_range_is_scene_order_inclusive(scene):
    out = _resolved(_recon_ir(range_from="A", range_to="C"), sess(scene))
    assert out.recon[0].zone_ids == ("ZONE_A", "ZONE_B", "ZONE_C")


def test_range_with_exclude(scene):
    out = _resolved(_recon_ir(range_from="A", range_to="D", exclude=("B",)), sess(scene))
    assert out.recon[0].zone_ids == ("ZONE_A", "ZONE_C", "ZONE_D")


@pytest.mark.parametrize(
    ("region", "expected"),
    [
        ("WEST", ("ZONE_A", "ZONE_C")),
        ("EAST", ("ZONE_B", "ZONE_D")),
        ("NORTH", ("ZONE_A", "ZONE_B")),
        ("SOUTH", ("ZONE_C", "ZONE_D")),
    ],
)
def test_region_is_a_scene_bbox_half_plane(scene, region, expected):
    out = _resolved(_recon_ir(region=region), sess(scene))
    assert out.recon[0].zone_ids == expected


def test_unvisited_only_drops_completed_recon(scene):
    from core.enums import TaskStatus, TaskType

    graph = compile_reference_graph(
        scene, [(TaskType.AREA_RECON, z) for z in ("ZONE_A", "ZONE_B", "ZONE_C", "ZONE_D")], [])
    for t in graph.tasks:
        if t.target in {"ZONE_A", "ZONE_B"}:
            t.status = TaskStatus.COMPLETED
    session = sess(scene, state=fresh_session_state(graph, scene))
    out = _resolved(_recon_ir(range_from="A", range_to="D", unvisited_only=True), session)
    assert out.recon[0].zone_ids == ("ZONE_C", "ZONE_D")


def test_empty_zone_result_clarifies(scene):
    out = resolve_mission_ir(_recon_ir(explicit=("B",), exclude=("B",)), sess(scene))
    assert out.status is GroundingStatus.CLARIFICATION_REQUIRED
    assert out.reason is ClarificationReason.NO_ENTITIES


def test_unknown_exclude_clarifies_not_silently_ignored(scene):
    out = resolve_mission_ir(_recon_ir(range_from="A", range_to="D", exclude=("ZONE_Z",)),
                             sess(scene))
    assert out.status is GroundingStatus.CLARIFICATION_REQUIRED
    assert out.reason is ClarificationReason.UNKNOWN_ENTITY


def test_backwards_range_clarifies(scene):
    out = resolve_mission_ir(_recon_ir(range_from="D", range_to="A"), sess(scene))
    assert out.status is GroundingStatus.CLARIFICATION_REQUIRED


# -- incident selectors --------------------------------------------


def _resp_ir(depth="GROUND_INSPECTION", **incident_kw):
    return SemanticMissionIR(responses=(ResponseClause(
        incidents=IncidentSelector(**incident_kw), response_up_to=depth),))


def test_all_known_incidents(scene):
    out = _resolved(_resp_ir(recency="ALL_KNOWN"), sess(scene))
    assert set(out.responses[0].incident_ids) == {"FIRE_SITE_1", "FIRE_SITE_2"}


def test_explicit_incident(scene):
    out = _resolved(_resp_ir(explicit=("FIRE_SITE_1",)), sess(scene))
    assert out.responses[0].incident_ids == ("FIRE_SITE_1",)


def test_spatial_pick_eastmost(scene):
    out = _resolved(_resp_ir(recency="ALL_KNOWN", spatial_pick="EASTMOST"), sess(scene))
    assert out.responses[0].incident_ids == ("FIRE_SITE_2",)   # x 205 > 128


def test_spatial_pick_northmost(scene):
    out = _resolved(_resp_ir(recency="ALL_KNOWN", spatial_pick="NORTHMOST"), sess(scene))
    assert out.responses[0].incident_ids == ("FIRE_SITE_1",)   # y 108 > 42


def _obs(zone, iid, t, source="SENSOR_SIMULATED"):
    return IncidentObservationAudit(
        session_id="RES", fixture_id="fx", zone_id=zone,
        trigger_task_id=f"AREA_RECON__{zone}", detecting_agent_id="U1",
        simulation_time=t, mode="mock", outcome="ADAPTED", incident_id=iid, source=source,
    )


def test_recent_incidents_uses_event_log_order_and_source(scene):
    session = sess(scene)
    session.append_event(_obs("ZONE_B", "FIRE_SITE_1", 10.0))
    session.append_event(_obs("ZONE_D", "FIRE_SITE_2", 20.0))

    out = _resolved(_resp_ir(recency="MOST_RECENT_DETECTED", recent_count=2,
                             recent_source="SENSOR"), session)
    assert out.responses[0].incident_ids == ("FIRE_SITE_2", "FIRE_SITE_1")  # newest first

    only_recent = _resolved(_resp_ir(recency="MOST_RECENT_DETECTED", recent_count=1,
                                     recent_source="SENSOR"), session)
    assert only_recent.responses[0].incident_ids == ("FIRE_SITE_2",)


def test_recent_incidents_source_filter_excludes_operator(scene):
    session = sess(scene)
    session.append_event(_obs("ZONE_B", "FIRE_SITE_1", 10.0, source="OPERATOR"))
    out = resolve_mission_ir(_resp_ir(recency="MOST_RECENT_DETECTED", recent_count=1,
                                      recent_source="SENSOR"), session)
    assert out.status is GroundingStatus.CLARIFICATION_REQUIRED  # nothing SENSOR-sourced


def test_recent_count_more_than_available_clarifies(scene):
    session = sess(scene)
    session.append_event(_obs("ZONE_B", "FIRE_SITE_1", 10.0))
    out = resolve_mission_ir(_resp_ir(recency="MOST_RECENT_DETECTED", recent_count=2),
                             session)
    assert out.status is GroundingStatus.CLARIFICATION_REQUIRED


# -- multi-clause (S4) --------------------------------------------


def test_same_incident_two_depths_is_a_semantic_conflict(scene):
    ir = SemanticMissionIR(responses=(
        ResponseClause(incidents=IncidentSelector(explicit=("FIRE_SITE_1",)),
                       response_up_to="GROUND_INSPECTION"),
        ResponseClause(incidents=IncidentSelector(explicit=("FIRE_SITE_1",)),
                       response_up_to="GROUND_SUPPRESSION"),
    ))
    out = resolve_mission_ir(ir, sess(scene))
    assert out.status is GroundingStatus.CLARIFICATION_REQUIRED
    assert out.reason is ClarificationReason.SEMANTIC_CONFLICT


def test_same_incident_same_depth_is_fine(scene):
    ir = SemanticMissionIR(responses=(
        ResponseClause(incidents=IncidentSelector(explicit=("FIRE_SITE_1",)),
                       response_up_to="GROUND_INSPECTION"),
        ResponseClause(incidents=IncidentSelector(recency="ALL_KNOWN"),
                       response_up_to="GROUND_INSPECTION"),
    ))
    out = _resolved(ir, sess(scene))
    assert {i for r in out.responses for i in r.incident_ids} == {
        "FIRE_SITE_1", "FIRE_SITE_2"}


def test_compositional_recon_plus_response(scene):
    ir = SemanticMissionIR(
        recon=(ReconClause(zones=ZoneSelector(range_from="A", range_to="C")),),
        responses=(ResponseClause(incidents=IncidentSelector(explicit=("FIRE_SITE_2",)),
                                  response_up_to="GROUND_SUPPRESSION"),),
    )
    out = _resolved(ir, sess(scene))
    assert out.recon[0].zone_ids == ("ZONE_A", "ZONE_B", "ZONE_C")
    assert out.responses[0].incident_ids == ("FIRE_SITE_2",)
    assert out.responses[0].response_up_to == "GROUND_SUPPRESSION"
