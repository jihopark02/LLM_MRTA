"""P8.1d: deterministic grounder + canonical patch builder (§18.5-§18.7, D-027).

Every clarification in the system originates here, so these tests are the real
gate on "asks instead of guessing". The four §18 worked examples each have a
case below.
"""

from pathlib import Path

import pytest

from core.enums import TaskType
from interaction.ground import (
    GroundingStatus,
    build_chain_patch,
    chain_prefix,
    resolve_incident,
    resolve_zone,
)
from interaction.scene_mut import register_incident
from interaction.session import MissionSession, ReferentKind
from scenarios.compiler import compile_reference_graph
from scenarios.scene import load_scene
from validator.patch import AddEdge, AddTask
from validator.patch_apply import apply_patch

SCENE = Path(__file__).parents[1] / "scenarios" / "industrial_park.yaml"

CHAIN = [
    TaskType.THERMAL_RECON,
    TaskType.SUPPRESSANT_DROP,
    TaskType.GROUND_INSPECTION,
    TaskType.GROUND_SUPPRESSION,
]


@pytest.fixture
def scene():
    return load_scene(SCENE)


def session(scene, **kw) -> MissionSession:
    return MissionSession(session_id="S1", scene=scene, **kw)


def graph_with(scene, incident_id, steps):
    specs = [(step, incident_id) for step in steps]
    edges = [
        ((a, incident_id), (b, incident_id))
        for a, b in zip(steps, steps[1:], strict=False)
    ]
    return compile_reference_graph(scene, specs, edges)


# -- zone resolution (§18.7) ------------------------------------------


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("ZONE_A", "ZONE_A"),
        ("zone_a", "ZONE_A"),
        ("A 구역", "ZONE_A"),
        ("A구역", "ZONE_A"),
        ("A", "ZONE_A"),
        ("Warehouse", "ZONE_A"),
        ("warehouse", "ZONE_A"),
        ("Processing Area", "ZONE_B"),
        ("processing area", "ZONE_B"),
        ("B 지역", "ZONE_B"),
        ("Utility Yard", "ZONE_C"),
        ("Tank Farm", "ZONE_D"),
        ("ZONE_D", "ZONE_D"),
    ],
)
def test_zone_aliases_resolve(scene, phrase, expected):
    out = resolve_zone(scene, phrase)
    assert out.resolved and out.entity_id == expected
    assert out.entity_kind is ReferentKind.ZONE


@pytest.mark.parametrize("phrase", [None, "", "   ", "ZONE_Z", "Nowhere", "구역"])
def test_unmatched_zone_clarifies_with_the_zone_list(scene, phrase):
    out = resolve_zone(scene, phrase)
    assert out.status is GroundingStatus.CLARIFICATION_REQUIRED
    assert out.entity_id is None
    assert out.candidates == ("ZONE_A", "ZONE_B", "ZONE_C", "ZONE_D")


# -- incident resolution (§18.5) --------------------------------------


def test_explicit_incident_id_resolves(scene):
    out = resolve_incident(session(scene), "FIRE_SITE_2")
    assert out.resolved and out.entity_id == "FIRE_SITE_2"
    assert out.entity_kind is ReferentKind.INCIDENT


def test_explicit_id_wins_over_a_recent_referent(scene):
    s = session(scene)
    s.note_referent("incident", "FIRE_SITE_1")
    assert resolve_incident(s, "FIRE_SITE_2").entity_id == "FIRE_SITE_2"


def test_unknown_but_incident_shaped_phrase_does_not_fall_through(scene):
    # Naming something specific that does not exist must not silently resolve
    # to whatever was mentioned last.
    s = session(scene)
    s.note_referent("incident", "FIRE_SITE_1")
    out = resolve_incident(s, "FIRE_SITE_9")
    assert out.status is GroundingStatus.CLARIFICATION_REQUIRED
    assert "FIRE_SITE_9" in out.clarification


def test_example_1_no_incident_registered_clarifies(tmp_path):
    # §18 example 1: "거기서 불이 난 곳을 꺼줘" with nothing reported.
    empty = tmp_path / "empty.yaml"
    empty.write_text(
        "scene_id: t\n"
        "zones: {ZONE_A: {name: A, recon_waypoint: [0, 0],"
        " reported_incident_position: [1, 1], reported_incident_access_node: N0}}\n"
        "incidents: {}\n"
        "route_graph: {nodes: {N0: [0, 0]}, lanes: []}\n"
        "fleet: []\n"
    )
    out = resolve_incident(session(load_scene(empty)), "거기")
    assert out.status is GroundingStatus.CLARIFICATION_REQUIRED
    assert "등록된 화재 지점이 없습니다" in out.clarification
    assert out.candidates == ()


def test_example_2_a_just_reported_incident_is_the_referent(scene):
    # §18 example 2: report in A, then "거기부터 확인하고 꺼줘".
    s = session(scene)
    new_scene, iid = register_incident(scene, "ZONE_A")
    s.scene = new_scene
    s.note_referent("incident", iid)

    out = resolve_incident(s, "거기")
    assert out.resolved and out.entity_id == iid  # the new one, not FIRE_SITE_1/2


def test_example_4_two_incidents_and_no_referent_clarifies(scene):
    # §18 example 4: "그 화재부터 처리해줘" with two registered and nothing recent.
    out = resolve_incident(session(scene), "그 화재")
    assert out.status is GroundingStatus.CLARIFICATION_REQUIRED
    assert out.candidates == ("FIRE_SITE_1", "FIRE_SITE_2")


def test_two_referents_on_the_same_turn_clarify(scene):
    s = session(scene)
    s.note_referent("incident", "FIRE_SITE_1")
    s.note_referent("incident", "FIRE_SITE_2")
    out = resolve_incident(s, "거기")
    assert out.status is GroundingStatus.CLARIFICATION_REQUIRED
    assert out.candidates == ("FIRE_SITE_1", "FIRE_SITE_2")


def test_an_expired_referent_no_longer_resolves(scene):
    s = session(scene)
    s.note_referent("incident", "FIRE_SITE_1")
    s.turn_count = 99  # far outside the K-turn window
    out = resolve_incident(s, "거기")
    assert out.status is GroundingStatus.CLARIFICATION_REQUIRED


def test_a_single_registered_incident_needs_no_referent(tmp_path):
    # Rule 5: with one incident there is nothing to choose between.
    one = tmp_path / "one.yaml"
    one.write_text(
        "scene_id: t\n"
        "zones: {ZONE_A: {name: A, recon_waypoint: [0, 0],"
        " reported_incident_position: [1, 1], reported_incident_access_node: N0}}\n"
        "incidents: {F1: {zone: ZONE_A, priority: 7, position: [1, 1], access_node: N0,"
        " status: RESPONSE_REQUIRED}}\n"
        "route_graph: {nodes: {N0: [0, 0]}, lanes: []}\n"
        "fleet: []\n"
    )
    out = resolve_incident(session(load_scene(one)), "그 화재")
    assert out.resolved and out.entity_id == "F1"


def test_grounding_never_mutates_the_session(scene):
    s = session(scene)
    s.note_referent("incident", "FIRE_SITE_1")
    before = (list(s.recent_referents), s.turn_count, s.scene, s.state)
    resolve_incident(s, "그 화재")
    resolve_incident(s, "FIRE_SITE_9")
    resolve_zone(s.scene, "nowhere")
    assert (list(s.recent_referents), s.turn_count, s.scene, s.state) == before


# -- canonical chain prefix ------------------------------------------


@pytest.mark.parametrize(
    ("step", "length"),
    [
        ("THERMAL_RECON", 1),
        ("SUPPRESSANT_DROP", 2),
        ("GROUND_INSPECTION", 3),
        ("GROUND_SUPPRESSION", 4),
    ],
)
def test_chain_prefix_is_contiguous(step, length):
    prefix = chain_prefix(step)
    assert len(prefix) == length
    assert list(prefix) == CHAIN[:length]


# -- patch builder: extending a new incident -------------------------


@pytest.mark.parametrize("upto_index", range(4))
def test_builds_the_missing_prefix_from_an_empty_graph(scene, upto_index):
    step = CHAIN[upto_index].value
    graph = compile_reference_graph(scene, [], [])
    plan = build_chain_patch(graph, "FIRE_SITE_1", step)

    assert not plan.no_change
    assert list(plan.added_steps) == CHAIN[: upto_index + 1]
    assert len(plan.added_edges) == upto_index
    assert sum(isinstance(o, AddTask) for o in plan.patch.operations) == upto_index + 1
    assert sum(isinstance(o, AddEdge) for o in plan.patch.operations) == upto_index


def test_extends_only_what_is_missing(scene):
    graph = graph_with(scene, "FIRE_SITE_1", CHAIN[:2])
    plan = build_chain_patch(graph, "FIRE_SITE_1", "GROUND_SUPPRESSION")
    assert list(plan.added_steps) == [TaskType.GROUND_INSPECTION, TaskType.GROUND_SUPPRESSION]
    assert len(plan.added_edges) == 2  # SD->GI and GI->GS


def test_built_patch_is_accepted_by_the_validator(scene):
    from interaction.session import fresh_session_state

    graph = graph_with(scene, "FIRE_SITE_1", CHAIN[:1])
    state = fresh_session_state(graph, scene)
    plan = build_chain_patch(state.graph, "FIRE_SITE_1", "GROUND_SUPPRESSION")

    new_state, result = apply_patch(state, plan.patch, scene)
    assert result.accepted, result.rejection_errors
    assert len(new_state.graph) == 4
    assert result.directly_released_tasks == ()  # canonical extension releases nothing


def test_built_patch_for_a_reported_incident_is_accepted(scene):
    from interaction.session import fresh_session_state

    new_scene, iid = register_incident(scene, "ZONE_C")
    graph = graph_with(new_scene, iid, CHAIN[:1])
    state = fresh_session_state(graph, new_scene)
    plan = build_chain_patch(state.graph, iid, "GROUND_SUPPRESSION")

    committed, result = apply_patch(state, plan.patch, new_scene)
    assert result.accepted, result.rejection_errors
    assert {t.priority for t in committed.graph.tasks} == {7}


def test_other_incidents_are_untouched(scene):
    graph = graph_with(scene, "FIRE_SITE_1", CHAIN[:1])
    plan = build_chain_patch(graph, "FIRE_SITE_2", "SUPPRESSANT_DROP")
    targets = {
        op.target for op in plan.patch.operations if isinstance(op, AddTask)
    }
    assert targets == {"FIRE_SITE_2"}


# -- NO_CHANGE (§18.6) ------------------------------------------------


def test_repeating_a_completed_request_is_no_change(scene):
    graph = graph_with(scene, "FIRE_SITE_1", CHAIN)
    plan = build_chain_patch(graph, "FIRE_SITE_1", "GROUND_SUPPRESSION")
    assert plan.no_change
    assert plan.patch is None
    assert plan.added_steps == () and plan.added_edges == ()
    assert "이미 계획에 포함" in plan.note


@pytest.mark.parametrize("step", ["THERMAL_RECON", "SUPPRESSANT_DROP", "GROUND_INSPECTION"])
def test_a_lower_step_than_planned_is_no_change_not_a_shrink(scene, step):
    # §18.6: nothing is removed in this scope.
    graph = graph_with(scene, "FIRE_SITE_1", CHAIN)
    plan = build_chain_patch(graph, "FIRE_SITE_1", step)
    assert plan.no_change


def test_no_change_never_produces_a_duplicate_add_task(scene):
    from interaction.session import fresh_session_state
    from validator.patch import MissionPatch

    graph = graph_with(scene, "FIRE_SITE_1", CHAIN[:2])
    plan = build_chain_patch(graph, "FIRE_SITE_1", "SUPPRESSANT_DROP")
    assert plan.no_change

    # The alternative the builder must never take: re-adding what exists.
    state = fresh_session_state(graph, scene)
    _, rejected = apply_patch(
        state, MissionPatch([AddTask(TaskType.SUPPRESSANT_DROP, "FIRE_SITE_1")]), scene
    )
    assert not rejected.accepted  # which is exactly why NO_CHANGE is returned


def test_missing_edge_alone_is_still_a_change(scene):
    # Defensive: tasks present but an edge absent is a real repair, not NO_CHANGE.
    graph = compile_reference_graph(
        scene,
        [(TaskType.THERMAL_RECON, "FIRE_SITE_1"), (TaskType.SUPPRESSANT_DROP, "FIRE_SITE_1")],
        [],
    )
    plan = build_chain_patch(graph, "FIRE_SITE_1", "SUPPRESSANT_DROP")
    assert not plan.no_change
    assert plan.added_steps == ()
    assert plan.added_edges == ((TaskType.THERMAL_RECON, TaskType.SUPPRESSANT_DROP),)


def test_builder_does_not_mutate_the_graph(scene):
    graph = graph_with(scene, "FIRE_SITE_1", CHAIN[:1])
    before = (len(graph), len(graph.edges))
    build_chain_patch(graph, "FIRE_SITE_1", "GROUND_SUPPRESSION")
    assert (len(graph), len(graph.edges)) == before
