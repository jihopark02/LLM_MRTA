"""P8.1a: planning-session state (RESEARCH_CONTRACT.md §18.5, §18.8, D-027).

Covers the two boundaries D-027 fixed: the session must not share a mutable
``Agent`` with the scene, and ``known_incident_ids`` / the LLM context must be
derived every time rather than stored.
"""

from pathlib import Path

import pytest

from core.enums import TaskType
from interaction.session import (
    REFERENT_WINDOW_TURNS,
    MissionSession,
    Referent,
    SessionPhase,
    build_context_summary,
    fresh_session_state,
)
from interaction.workflow import WORKFLOW_CHAIN
from scenarios.fixture import load_reference_fixture
from scenarios.scene import load_scene

SCENE = Path(__file__).parents[1] / "scenarios" / "industrial_park.yaml"


@pytest.fixture(scope="module")
def scene():
    return load_scene(SCENE)


@pytest.fixture(scope="module")
def fixture_graph():
    return load_reference_fixture().graph


def session(scene, **kw) -> MissionSession:
    return MissionSession(session_id="S1", scene=scene, **kw)


# -- workflow chain ---------------------------------------------------


def test_workflow_chain_matches_the_validator_rule():
    # interaction/workflow.py asserts this at import; make it an explicit gate.
    assert WORKFLOW_CHAIN == (
        TaskType.THERMAL_RECON,
        TaskType.SUPPRESSANT_DROP,
        TaskType.GROUND_INSPECTION,
        TaskType.GROUND_SUPPRESSION,
    )


# -- fresh_session_state: no shared mutable state with the scene (§18.8) --


def test_fresh_session_state_clones_the_graph(scene, fixture_graph):
    state = fresh_session_state(fixture_graph, scene)
    assert state.graph is not fixture_graph
    assert len(state.graph) == len(fixture_graph)

    tid = next(iter(sorted(t.task_id for t in fixture_graph.tasks)))
    state.graph[tid].assigned_agent = "S1"
    assert fixture_graph[tid].assigned_agent is None


def test_fresh_session_state_does_not_share_agents_with_the_scene(scene, fixture_graph):
    state = fresh_session_state(fixture_graph, scene)
    scene_agents = {a.agent_id: a for a in scene.fleet}
    assert set(state.agents) == set(scene_agents)

    for agent_id, agent in state.agents.items():
        assert agent is not scene_agents[agent_id]
        assert agent.bundle is not scene_agents[agent_id].bundle
        assert agent.path is not scene_agents[agent_id].path

    state.agents["S1"].bundle.append("AREA_RECON__ZONE_A")
    state.agents["S1"].current_task = "AREA_RECON__ZONE_A"
    assert scene_agents["S1"].bundle == []
    assert scene_agents["S1"].current_task is None


def test_fresh_session_state_starts_unallocated(scene, fixture_graph):
    state = fresh_session_state(fixture_graph, scene)
    assert state.winning_bids == {}
    assert all(not a.bundle and not a.path for a in state.agents.values())


# -- derived, never stored (D-027) -----------------------------------


def test_known_incident_ids_are_derived_from_the_scene(scene):
    s = session(scene)
    assert s.known_incident_ids == ["FIRE_SITE_1", "FIRE_SITE_2"]
    # swapping the scene changes the answer with no session bookkeeping
    from dataclasses import replace as dc_replace

    trimmed = dc_replace(scene, incidents={"FIRE_SITE_1": scene.incidents["FIRE_SITE_1"]})
    s.scene = trimmed
    assert s.known_incident_ids == ["FIRE_SITE_1"]


def test_context_for_llm_delegates_to_build_context_summary(scene):
    s = session(scene)
    assert s.context_for_llm() == build_context_summary(s)


# -- referents (§18.5) -----------------------------------------------


def test_note_referent_records_the_current_turn(scene):
    s = session(scene)
    s.turn_count = 2
    s.note_referent("incident", "FIRE_SITE_1")
    assert s.recent_referents == [Referent("incident", "FIRE_SITE_1", 2)]


def test_referents_expire_after_the_window(scene):
    s = session(scene)
    s.turn_count = 1
    s.note_referent("incident", "FIRE_SITE_1")

    s.turn_count = 1 + (REFERENT_WINDOW_TURNS - 1)  # still inside the window
    assert [r.entity_id for r in s.live_referents()] == ["FIRE_SITE_1"]

    s.turn_count += 1  # one turn too far
    assert s.live_referents() == []


def test_live_referents_filter_by_kind(scene):
    s = session(scene)
    s.note_referent("incident", "FIRE_SITE_1")
    s.note_referent("zone", "ZONE_A")
    assert [r.entity_id for r in s.live_referents("incident")] == ["FIRE_SITE_1"]
    assert [r.entity_id for r in s.live_referents("zone")] == ["ZONE_A"]


def test_two_referents_on_the_same_turn_are_ambiguous(scene):
    # §18.5: the grounder must clarify rather than pick one.
    s = session(scene)
    s.note_referent("incident", "FIRE_SITE_2")
    s.note_referent("incident", "FIRE_SITE_1")
    assert s.latest_referent_candidates("incident") == ["FIRE_SITE_1", "FIRE_SITE_2"]


def test_newer_turn_wins_over_an_older_one(scene):
    s = session(scene)
    s.note_referent("incident", "FIRE_SITE_1")
    s.turn_count = 1
    s.note_referent("incident", "FIRE_SITE_2")
    assert s.latest_referent_candidates("incident") == ["FIRE_SITE_2"]


def test_no_referents_yields_no_candidates(scene):
    assert session(scene).latest_referent_candidates("incident") == []


# -- context summary (§18.3) -----------------------------------------


def test_context_summary_is_deterministic(scene, fixture_graph):
    s = session(scene, state=fresh_session_state(fixture_graph, scene))
    assert build_context_summary(s) == build_context_summary(s)


def test_context_summary_without_a_mission(scene):
    text = build_context_summary(session(scene))
    assert "PHASE: PLANNING" in text
    assert "ZONES: ZONE_A, ZONE_B, ZONE_C, ZONE_D" in text
    assert "FIRE_SITE_1 (zone ZONE_B, priority 9, RESPONSE_REQUIRED)" in text
    assert "MISSION: none" in text
    assert "RECENT REFERENTS: none" in text


def test_context_summary_shows_chain_progress(scene, fixture_graph):
    s = session(scene, state=fresh_session_state(fixture_graph, scene))
    text = build_context_summary(s)
    assert "MISSION: 12 tasks, 6 edges" in text
    assert "AREA_RECON: ZONE_A, ZONE_B, ZONE_C, ZONE_D" in text
    assert (
        "FIRE_SITE_1: THERMAL_RECON -> SUPPRESSANT_DROP -> "
        "GROUND_INSPECTION -> GROUND_SUPPRESSION" in text
    )
    assert "status: PENDING 6, READY 6" in text


def test_context_summary_reports_an_empty_incident_list(tmp_path):
    # §18 example 1: with nothing registered the operator must be told so.
    empty = tmp_path / "empty.yaml"
    empty.write_text(
        "scene_id: t\n"
        "zones: {ZONE_A: {name: A, recon_waypoint: [0, 0]}}\n"
        "incidents: {}\n"
        "route_graph: {nodes: {N0: [0, 0]}, lanes: []}\n"
        "fleet:\n"
        "  - {agent_id: S1, platform_kind: UAV, capabilities: [AERIAL_RECON],"
        " position: [0, 0], speed: 8}\n"
    )
    s = session(load_scene(empty))
    text = build_context_summary(s)
    assert "(none registered)" in text
    assert "MISSION: none" in text


def test_context_summary_lists_live_referents(scene):
    s = session(scene)
    s.note_referent("incident", "FIRE_SITE_2")
    assert "RECENT REFERENTS: FIRE_SITE_2 (incident, turn 0)" in build_context_summary(s)


def test_phase_values(scene):
    assert session(scene).phase is SessionPhase.PLANNING
    assert [p.value for p in SessionPhase] == ["PLANNING", "EXECUTED", "EXECUTION_FAILED"]
