"""P8.2 gate: the planning-session turn loop (§18.3, §18.4, §18.9, D-027/D-028).

The I1-I8 matrix from the P8 design, plus the invariants the orchestrator is
the single owner of. Everything runs headless on scripted MockBackend
responses — no network, no API key.

D-076: NEW_MISSION / UPDATE_MISSION carry a Semantic Mission IR; the runtime no
longer calls generate_mission. A resolver clarification for a mission-editing
act is fail-closed and non-resumable (S8) — nothing is partially committed and
the operator restates. The resumable-candidate path keeps only the grounder's
single-slot ambiguities (REPORT_INCIDENT zone_ref, QUERY_STATUS target_phrase).
"""

from dataclasses import replace
from pathlib import Path

import pytest

from interaction.audit import ExecutionAudit, PlanAssignmentChanges, TurnAudit
from interaction.directive import MissionDirective
from interaction.ground import ResolutionVia
from interaction.orchestrator import (
    TurnOutcome,
    cancel_clarification,
    handle_turn,
    select_clarification_candidate,
)
from interaction.schemas import wire_intent
from interaction.session import MissionSession, SessionPhase
from llm.backend import MockBackend
from scenarios.scene import load_scene
from tests.ir_fixtures import mission_ir, policy, recon, response, response_ir

SCENE = Path(__file__).parents[1] / "scenarios" / "industrial_park.yaml"

CHAIN = ["GROUND_INSPECTION", "GROUND_SUPPRESSION"]


@pytest.fixture
def scene():
    return load_scene(SCENE)


def sess(scene, **kw) -> MissionSession:
    return MissionSession(session_id="S1", scene=scene, **kw)


def intent(kind: str, **slots) -> "wire_intent":
    return wire_intent(kind, **slots)


def new_mission(mission=None, **slots):
    return wire_intent(
        "NEW_MISSION",
        mission=mission or response_ir("GROUND_SUPPRESSION", explicit=("FIRE_SITE_1",)),
        **slots,
    )


def update_mission(mission, **slots):
    return wire_intent("UPDATE_MISSION", mission=mission, **slots)


def resp_update(incident_id_or_deixis, up_to="GROUND_SUPPRESSION", *, deixis=False):
    key = "deixis" if deixis else "explicit"
    kw = {key: incident_id_or_deixis} if deixis else {key: (incident_id_or_deixis,)}
    return update_mission(response_ir(up_to, **kw))


def start_mission(session, incident_id="FIRE_SITE_1", steps=CHAIN):
    m = response_ir(steps[-1], explicit=(incident_id,))
    result = handle_turn(
        session, f"{incident_id} 대응 시작", MockBackend([new_mission(m)])
    )
    assert result.outcome is TurnOutcome.COMMITTED, result.message
    return result


def _dup_zone_scene(scene):
    """ZONE_A and ZONE_B both named 'Shared' — a genuine grounder ambiguity that
    still creates a resumable pending (REPORT_INCIDENT zone_ref)."""
    return replace(
        scene,
        zones={
            **scene.zones,
            "ZONE_A": replace(scene.zones["ZONE_A"], name="Shared"),
            "ZONE_B": replace(scene.zones["ZONE_B"], name="Shared"),
        },
    )


# -- P12.1: initial graph and future-incident policy are separate ----------


def test_new_mission_commits_the_llm_extracted_incident_policy_with_the_graph(scene):
    s = sess(scene)
    m = mission_ir(
        responses=(response("GROUND_INSPECTION", explicit=("FIRE_SITE_1",)),),
        incident_policy=policy("GROUND_SUPPRESSION"),
    )

    result = handle_turn(s, "화재가 발견되면 지상 진압까지 대응해줘", MockBackend([new_mission(m)]))

    assert result.outcome is TurnOutcome.COMMITTED
    assert s.directive == MissionDirective.from_slot("GROUND_SUPPRESSION")
    assert len(s.state.graph) == 1  # the future policy did not invent future tasks


def test_new_mission_without_a_conditional_clause_has_no_incident_policy(scene):
    s = sess(scene)
    start_mission(s, steps=["GROUND_INSPECTION"])
    assert s.directive == MissionDirective()


# -- I1: ambiguous first command, then a deixis with nothing registered ----


def test_i1_deixis_with_no_incident_clarifies_and_changes_nothing(tmp_path):
    empty = tmp_path / "empty.yaml"
    empty.write_text(
        "scene_id: t\n"
        "zones: {ZONE_A: {name: A, recon_waypoint: [0, 0],"
        " reported_incident_position: [1, 1], reported_incident_access_node: N0}}\n"
        "incidents: {}\n"
        "route_graph: {nodes: {N0: [0, 0]}, lanes: []}\n"
        "fleet: []\n"
    )
    s = sess(load_scene(empty))
    scene_before, state_before = s.scene, s.state

    r = handle_turn(
        s, "거기서 불이 난 곳을 꺼줘", MockBackend([resp_update("거기", deixis=True)])
    )

    assert r.outcome is TurnOutcome.CLARIFICATION
    assert "임무가 없습니다" in r.message  # no mission yet, so that is the first gap
    assert s.scene is scene_before and s.state is state_before
    assert s.recent_referents == []


# -- I2: report, then a deixis that must ground to the new incident -------


def test_i2_report_then_deixis_extends_the_new_incident(scene):
    s = sess(scene)
    start_mission(s)  # a mission must exist for UPDATE (§18.4)

    r1 = handle_turn(
        s, "A 구역에서 화재가 보고됐어", MockBackend([intent("REPORT_INCIDENT", zone_ref="A 구역")])
    )
    assert r1.outcome is TurnOutcome.COMMITTED
    assert "FIRE_SITE_3" in s.known_incident_ids
    assert r1.audit.scene_changed and not r1.audit.state_changed
    assert r1.audit.referent_noted == "FIRE_SITE_3"

    r2 = handle_turn(
        s, "거기부터 확인하고 불을 꺼줘", MockBackend([resp_update("거기", deixis=True)])
    )
    assert r2.outcome is TurnOutcome.COMMITTED
    assert r2.audit.semantic_ir.responses[0].targets == ["FIRE_SITE_3"]
    assert r2.patch_result.accepted
    assert [t.target for t in s.state.graph.tasks].count("FIRE_SITE_3") == 2
    assert r2.patch_result.directly_released_tasks == ()


# -- I3: read-only status query ------------------------------------------


def test_i3_query_status_answers_without_touching_anything(scene):
    s = sess(scene)
    start_mission(s)
    scene_before, state_before, plan_before = s.scene, s.state, s.plan

    r = handle_turn(
        s,
        "현재 어떤 로봇이 화재 대응 중이야?",
        MockBackend([intent("QUERY_STATUS", about="agents")]),
    )
    assert r.outcome is TurnOutcome.ANSWERED
    assert r.audit.answer and "GROUND_INSPECTION__FIRE_SITE_1" in r.audit.answer
    assert s.scene is scene_before and s.state is state_before
    assert s.plan is plan_before  # no re-allocation for a read
    assert not r.audit.state_changed and not r.audit.scene_changed


def test_query_before_any_mission_is_answered_not_an_error(scene):
    s = sess(scene)
    r = handle_turn(s, "지금 상황 어때?", MockBackend([intent("QUERY_STATUS")]))
    assert r.outcome is TurnOutcome.ANSWERED
    assert "활성 임무가 없습니다" in r.message
    assert s.state is None


# -- I4: two incidents, no referent — S8 fail-closed, non-resumable ------


def test_i4_ambiguous_referent_is_a_non_resumable_clarification(scene):
    s = sess(scene)
    start_mission(s)
    state_before = s.state

    r = handle_turn(s, "그 화재부터 처리해줘", MockBackend([resp_update("그 화재", deixis=True)]))

    assert r.outcome is TurnOutcome.CLARIFICATION
    assert "다시 말씀" in r.message  # restate the whole request, not "pick one"
    assert s.state is state_before
    assert s.recent_referents == []
    assert s.pending_clarification is None  # S8: no resumable candidate for a mission edit


def test_i4_unknown_referent_also_clarifies_without_locking_the_session(scene):
    s = sess(scene)
    start_mission(s)
    r = handle_turn(s, "북쪽 화재를 처리해줘", MockBackend([resp_update("북쪽 화재", deixis=True)]))
    assert r.audit.grounding.reason == "UNKNOWN_ENTITY"
    assert s.pending_clarification is None
    assert s.state is not None  # unchanged


def test_update_mission_ambiguity_commits_no_clause_atomically(scene):
    # A multi-clause edit where one clause is ambiguous rejects the whole IR.
    s = sess(scene)
    start_mission(s, steps=CHAIN[:1])
    before = len(s.state.graph)
    m = mission_ir(
        recon=(recon(range_from="A", range_to="C"),),          # fine on its own
        responses=(response("GROUND_SUPPRESSION", deixis="그 화재"),),  # ambiguous
    )
    r = handle_turn(s, "A~C 정찰하고 그 화재 진압", MockBackend([update_mission(m)]))

    assert r.outcome is TurnOutcome.CLARIFICATION
    assert len(s.state.graph) == before  # the recon clause was not partially applied
    assert s.pending_clarification is None


# -- resumable candidate path (REPORT_INCIDENT / QUERY_STATUS only) ------


def _start_ambiguous_report(session):
    backend = MockBackend([intent("REPORT_INCIDENT", zone_ref="Shared 구역")])
    result = handle_turn(session, "Shared 구역에 불", backend)
    assert result.outcome is TurnOutcome.CLARIFICATION
    assert session.pending_clarification is not None
    return result


def test_pending_natural_language_is_audited_without_calling_the_backend(scene):
    s = sess(_dup_zone_scene(scene))
    _start_ambiguous_report(s)
    pending = s.pending_clarification
    backend = MockBackend([intent("QUERY_STATUS")])

    r = handle_turn(s, "아니 다른 말", backend)

    assert backend.calls == []
    assert r.outcome is TurnOutcome.CLARIFICATION
    assert r.audit.grounding.reason == "PENDING_SELECTION"
    assert r.audit.input_kind == "NATURAL_LANGUAGE"
    assert r.audit.resumed_from_turn_id == pending.source_turn_id
    assert s.pending_clarification is pending


def test_valid_candidate_resumes_the_report_without_an_llm_call(scene):
    s = sess(_dup_zone_scene(scene))
    source = _start_ambiguous_report(s)
    turn_count = s.turn_count

    r = select_clarification_candidate(s, "ZONE_B", mode="mock")

    assert r.outcome is TurnOutcome.COMMITTED
    assert s.turn_count == turn_count + 1
    assert s.pending_clarification is None
    assert r.audit.resolved_models == []
    assert r.audit.input_kind == "CANDIDATE_SELECTION"
    assert r.audit.resumed_from_turn_id == source.audit.turn_id
    assert r.audit.selected_entity_id == "ZONE_B"
    assert s.scene.incidents["FIRE_SITE_3"].zone == "ZONE_B"
    assert r.audit.referent_noted == "FIRE_SITE_3"


def test_invalid_candidate_is_audited_and_keeps_the_pending_request(scene):
    s = sess(_dup_zone_scene(scene))
    _start_ambiguous_report(s)
    pending = s.pending_clarification

    r = select_clarification_candidate(s, "ZONE_Z", mode="mock")

    assert r.outcome is TurnOutcome.CLARIFICATION
    assert r.audit.grounding.reason == "INVALID_SELECTION"
    assert r.audit.selected_entity_id == "ZONE_Z"
    assert r.audit.resolved_models == []
    assert s.pending_clarification is pending


def test_cancel_is_an_audited_turn_that_only_clears_pending(scene):
    s = sess(_dup_zone_scene(scene))
    _start_ambiguous_report(s)
    state, plan, current_scene = s.state, s.plan, s.scene
    referents = list(s.recent_referents)
    source_turn_id = s.pending_clarification.source_turn_id

    r = cancel_clarification(s, mode="cached")

    assert r.outcome is TurnOutcome.CLARIFICATION_CANCELLED
    assert r.audit.input_kind == "CLARIFICATION_CANCEL"
    assert r.audit.mode == "cached"
    assert r.audit.resumed_from_turn_id == source_turn_id
    assert r.audit.resolved_models == []
    assert s.pending_clarification is None
    assert (s.state, s.plan, s.scene) == (state, plan, current_scene)
    assert s.recent_referents == referents


def test_candidate_processing_failure_keeps_pending_and_previous_state(scene, monkeypatch):
    from interaction import orchestrator

    s = sess(_dup_zone_scene(scene))
    _start_ambiguous_report(s)
    pending = s.pending_clarification
    scene_before = s.scene
    monkeypatch.setattr(
        orchestrator,
        "prepare_incident_transaction",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    r = select_clarification_candidate(s, "ZONE_B", mode="mock")

    assert r.outcome is TurnOutcome.TURN_ERROR
    assert s.pending_clarification is pending
    assert s.scene is scene_before


def test_candidate_selection_for_a_query_is_an_explicit_fresh_referent(scene):
    s = sess(scene)
    first = handle_turn(
        s,
        "그 화재 상태",
        MockBackend([intent("QUERY_STATUS", about="agents", target_phrase="그 화재")]),
    )
    assert first.outcome is TurnOutcome.CLARIFICATION

    selected = select_clarification_candidate(s, "FIRE_SITE_2", mode="mock")

    assert selected.outcome is TurnOutcome.ANSWERED
    assert selected.audit.grounding.via == "explicit"
    assert selected.audit.referent_noted == "FIRE_SITE_2"
    assert s.recent_referents[-1].introduced_turn == s.turn_count


@pytest.mark.parametrize("bad_mode", [None, "LIVE", "", [], True])
def test_deterministic_clarification_actions_require_an_exact_mode(scene, bad_mode):
    s = sess(_dup_zone_scene(scene))
    _start_ambiguous_report(s)
    turn_count = s.turn_count

    with pytest.raises(ValueError, match="mode"):
        select_clarification_candidate(s, "ZONE_B", mode=bad_mode)
    assert s.turn_count == turn_count


def test_clarification_actions_require_a_pending_request(scene):
    s = sess(scene)
    with pytest.raises(ValueError, match="no clarification"):
        select_clarification_candidate(s, "FIRE_SITE_1", mode="mock")
    with pytest.raises(ValueError, match="no clarification"):
        cancel_clarification(s, mode="mock")
    assert s.turn_count == 0 and s.event_log == ()


# -- I5: extending an existing chain -------------------------------------


def test_i5_extends_a_partial_chain(scene):
    s = sess(scene)
    start_mission(s, steps=CHAIN[:1])
    assert len(s.state.graph) == 1

    r = handle_turn(
        s, "FIRE_SITE_1 지상 진압까지 해줘", MockBackend([resp_update("FIRE_SITE_1")])
    )
    assert r.outcome is TurnOutcome.COMMITTED
    assert len(s.state.graph) == 2
    assert r.audit.patch.added_tasks == ["GROUND_SUPPRESSION__FIRE_SITE_1"]


def test_update_can_add_recon_and_a_response_in_one_turn(scene):
    s = sess(scene)
    start_mission(s, steps=CHAIN[:1])
    before = len(s.state.graph)
    m = mission_ir(
        recon=(recon(range_from="A", range_to="B"),),
        responses=(response("GROUND_SUPPRESSION", explicit=("FIRE_SITE_1",)),),
    )
    r = handle_turn(s, "A~B 정찰하고 1번 진압까지", MockBackend([update_mission(m)]))

    assert r.outcome is TurnOutcome.COMMITTED
    added = {t.target for t in s.state.graph.tasks} - {"FIRE_SITE_1"}
    assert {"ZONE_A", "ZONE_B"} <= added
    assert len(s.state.graph) == before + 3  # 2 recon + 1 suppression


# -- I6: an update the Validator refuses ---------------------------------


def test_i6_rejected_patch_leaves_the_state_untouched(scene, monkeypatch):
    from core.enums import TaskType
    from interaction import orchestrator
    from validator.patch import AddEdge, MissionPatch

    s = sess(scene)
    start_mission(s, steps=CHAIN[:1])
    state_before, plan_before = s.state, s.plan

    # A cross-incident edge is exactly what the compiler never emits, so force
    # one in to prove the orchestrator does not commit a rejection.
    def cross_incident(ir, current):
        return MissionPatch(
            [
                AddEdge(
                    (TaskType.GROUND_INSPECTION, "FIRE_SITE_1"),
                    (TaskType.GROUND_INSPECTION, "FIRE_SITE_2"),
                )
            ]
        )

    monkeypatch.setattr(orchestrator, "compile_patch", cross_incident)
    r = handle_turn(s, "FIRE_SITE_1 진압까지", MockBackend([resp_update("FIRE_SITE_1")]))

    assert r.outcome is TurnOutcome.REJECTED
    assert not r.patch_result.accepted
    assert s.state is state_before and s.plan is plan_before
    assert s.recent_referents == []  # a failed UPDATE adds no referent (§18.5)
    assert r.audit.patch_hash and r.audit.pre_state_hash  # audit pair still recorded


def test_new_mission_compiler_bug_is_a_rejection_not_a_commit(scene, monkeypatch):
    from core.enums import TaskType
    from interaction import orchestrator
    from scenarios.compiler import compile_reference_graph

    s = sess(scene)

    def bad_graph(ir, sc):
        # a cross-incident edge — a Validator invariant the compiler must never break
        return compile_reference_graph(
            sc,
            [(TaskType.GROUND_INSPECTION, "FIRE_SITE_1"),
             (TaskType.GROUND_INSPECTION, "FIRE_SITE_2")],
            [((TaskType.GROUND_INSPECTION, "FIRE_SITE_1"),
              (TaskType.GROUND_INSPECTION, "FIRE_SITE_2"))],
        )

    monkeypatch.setattr(orchestrator, "compile_new_graph", bad_graph)
    r = handle_turn(s, "임무 시작", MockBackend([new_mission()]))

    assert r.outcome is TurnOutcome.REJECTED
    assert "Validator invariant" in r.message
    assert s.state is None and s.plan is None


# -- I7: report into a zone that does not exist --------------------------


def test_i7_unknown_zone_report_clarifies_and_leaves_the_scene(scene):
    s = sess(scene)
    scene_before = s.scene
    r = handle_turn(
        s, "Z 구역에 불이 났어", MockBackend([intent("REPORT_INCIDENT", zone_ref="Z 구역")])
    )

    assert r.outcome is TurnOutcome.CLARIFICATION
    assert r.grounding.candidates == ("ZONE_A", "ZONE_B", "ZONE_C", "ZONE_D")
    assert s.scene is scene_before
    assert s.known_incident_ids == ["FIRE_SITE_1", "FIRE_SITE_2"]


# -- I8: unsupported ------------------------------------------------------


def test_i8_unsupported_uses_a_fixed_template(scene):
    s = sess(scene)
    start_mission(s)
    scene_before, state_before = s.scene, s.state

    r = handle_turn(
        s,
        "G1한테 저 작업 취소시켜",
        MockBackend([intent("UNSUPPORTED", note="cancel + name an agent")]),
    )
    assert r.outcome is TurnOutcome.UNSUPPORTED
    assert "지원 범위 밖" in r.message
    assert "cancel" not in r.message  # the model's note is audit-only (§18.2)
    assert r.audit.extracted_slots.get("note") == "cancel + name an agent"
    assert s.scene is scene_before and s.state is state_before


# -- NO_CHANGE (§18.6) ---------------------------------------------------


def test_no_change_keeps_identity_and_does_not_replan(scene):
    s = sess(scene)
    start_mission(s)
    state_before, plan_before = s.state, s.plan

    r = handle_turn(
        s, "FIRE_SITE_1 다시 지상 진압까지 처리해줘", MockBackend([resp_update("FIRE_SITE_1")])
    )
    assert r.outcome is TurnOutcome.NO_CHANGE
    assert s.state is state_before and s.plan is plan_before
    assert r.patch_result is None  # no patch was even attempted
    assert not r.audit.state_changed


def test_no_change_still_keeps_the_referent_for_the_next_turn(scene):
    # §18.5: the UPDATE grounded correctly; only failures drop the referent.
    s = sess(scene)
    start_mission(s)
    handle_turn(s, "FIRE_SITE_1 진압까지", MockBackend([resp_update("FIRE_SITE_1")]))
    assert s.recent_referents[-1].entity_id == "FIRE_SITE_1"

    r = handle_turn(
        s, "거기 상태 알려줘", MockBackend([intent("QUERY_STATUS", target_phrase="거기")])
    )
    assert r.outcome is TurnOutcome.ANSWERED
    assert r.grounding.entity_id == "FIRE_SITE_1"


def test_a_lower_step_request_is_no_change_not_a_shrink(scene):
    s = sess(scene)
    start_mission(s)
    before = len(s.state.graph)
    r = handle_turn(
        s, "FIRE_SITE_1은 확인만 해", MockBackend([resp_update("FIRE_SITE_1", "GROUND_INSPECTION")])
    )
    assert r.outcome is TurnOutcome.NO_CHANGE
    assert len(s.state.graph) == before


# -- lifecycle (§18.4) ----------------------------------------------------


def test_new_mission_when_one_exists_does_not_replace_it(scene):
    s = sess(scene)
    start_mission(s)
    state_before = s.state
    r = handle_turn(s, "처음부터 다시 만들어줘", MockBackend([new_mission()]))
    assert r.outcome is TurnOutcome.CLARIFICATION
    assert s.state is state_before


def test_update_without_a_mission_clarifies(scene):
    s = sess(scene)
    r = handle_turn(s, "FIRE_SITE_1 진압까지", MockBackend([resp_update("FIRE_SITE_1")]))
    assert r.outcome is TurnOutcome.CLARIFICATION
    assert "활성 임무가 없습니다" in r.message
    assert s.state is None


@pytest.mark.parametrize("kind", ["NEW_MISSION", "REPORT_INCIDENT", "UPDATE_MISSION"])
@pytest.mark.parametrize("phase", [SessionPhase.EXECUTED, SessionPhase.EXECUTION_FAILED])
def test_planning_acts_are_unsupported_after_execution(scene, kind, phase):
    s = sess(scene, phase=phase)
    scene_before, state_before = s.scene, s.state
    if kind == "NEW_MISSION":
        env = new_mission()
    elif kind == "REPORT_INCIDENT":
        env = intent("REPORT_INCIDENT", zone_ref="A")
    else:
        env = resp_update("FIRE_SITE_1", "GROUND_INSPECTION")
    r = handle_turn(s, "뭔가 해줘", MockBackend([env]))
    assert r.outcome is TurnOutcome.UNSUPPORTED
    assert "새 세션" in r.message
    assert s.scene is scene_before and s.state is state_before


def test_query_is_still_allowed_after_execution(scene):
    s = sess(scene, phase=SessionPhase.EXECUTED)
    r = handle_turn(s, "결과 알려줘", MockBackend([intent("QUERY_STATUS")]))
    assert r.outcome is TurnOutcome.ANSWERED


# -- turn_count and referent ownership ------------------------------------


def test_turn_count_advances_exactly_once_per_turn(scene):
    s = sess(scene)
    assert s.turn_count == 0
    start_mission(s)
    assert s.turn_count == 1
    handle_turn(s, "상태", MockBackend([intent("QUERY_STATUS")]))
    assert s.turn_count == 2
    handle_turn(s, "아무거나", MockBackend([intent("UNSUPPORTED")]))
    assert s.turn_count == 3
    assert [a.turn_id for a in s.turn_log] == ["t1", "t2", "t3"]


@pytest.mark.parametrize(
    ("kind", "env_factory"),
    [
        ("UNSUPPORTED", lambda: wire_intent("UNSUPPORTED")),
        ("QUERY_STATUS", lambda: wire_intent("QUERY_STATUS")),
        ("UPDATE_MISSION", lambda: resp_update("그 화재", "GROUND_INSPECTION", deixis=True)),
        ("REPORT_INCIDENT", lambda: wire_intent("REPORT_INCIDENT", zone_ref="없는구역")),
    ],
)
def test_no_referent_is_added_on_a_non_grounded_turn(scene, kind, env_factory):
    s = sess(scene)
    start_mission(s)
    before = list(s.recent_referents)
    handle_turn(s, "...", MockBackend([env_factory()]))
    assert s.recent_referents == before


def test_referents_only_ever_come_from_the_orchestrator(scene):
    s = sess(scene)
    start_mission(s)
    handle_turn(
        s, "A 구역 화재", MockBackend([intent("REPORT_INCIDENT", zone_ref="A 구역")])
    )
    handle_turn(
        s, "거기 상태", MockBackend([intent("QUERY_STATUS", target_phrase="거기")])
    )
    assert all(r.entity_id in s.scene.incidents for r in s.recent_referents)
    assert all(r.introduced_turn <= s.turn_count for r in s.recent_referents)


# -- allocate only on a real graph change ---------------------------------


def test_allocate_runs_only_when_the_graph_changed(scene, monkeypatch):
    from interaction import orchestrator

    calls = []
    real = orchestrator.allocate

    def counting(state, sc):
        calls.append(1)
        return real(state, sc)

    monkeypatch.setattr(orchestrator, "allocate", counting)

    s = sess(scene)
    start_mission(s, steps=CHAIN[:1])
    assert len(calls) == 1                                    # NEW_MISSION committed

    handle_turn(s, "상태", MockBackend([intent("QUERY_STATUS")]))
    handle_turn(s, "아무거나", MockBackend([intent("UNSUPPORTED")]))
    handle_turn(
        s, "B 구역 화재", MockBackend([intent("REPORT_INCIDENT", zone_ref="B 구역")])
    )
    assert len(calls) == 1                                    # scene-only, no graph change

    handle_turn(
        s, "FIRE_SITE_1 확인만", MockBackend([resp_update("FIRE_SITE_1", "GROUND_INSPECTION")])
    )
    assert len(calls) == 1                                    # NO_CHANGE

    handle_turn(s, "FIRE_SITE_1 진압까지", MockBackend([resp_update("FIRE_SITE_1")]))
    assert len(calls) == 2                                    # committed patch


# -- audit (§18.9) --------------------------------------------------------


def test_every_turn_appends_a_typed_audit_record(scene):
    s = sess(scene)
    start_mission(s)
    handle_turn(s, "상태", MockBackend([intent("QUERY_STATUS")]))
    assert len(s.turn_log) == 2
    assert all(isinstance(a, TurnAudit) for a in s.turn_log)
    assert all(a.session_id == "S1" for a in s.turn_log)
    assert all(a.to_dict()["event_type"] == "TURN" for a in s.turn_log)


def test_new_mission_audit_carries_semantic_ir_provenance(scene):
    s = sess(scene)
    m = mission_ir(
        recon=(recon(range_from="A", range_to="C", exclude=("B",)),),
        responses=(response("GROUND_SUPPRESSION", explicit=("FIRE_SITE_1",)),),
    )
    r = handle_turn(s, "A~C 정찰(B 제외)하고 1번 진압", MockBackend([new_mission(m)]))

    sir = r.audit.semantic_ir
    assert sir.recon[0].operator == "RANGE(A..C) EXCLUDE(B)"
    assert sir.recon[0].targets == ["ZONE_A", "ZONE_C"]
    assert sir.responses[0].operator == "EXPLICIT(FIRE_SITE_1) -> GROUND_SUPPRESSION"
    assert sir.responses[0].targets == ["FIRE_SITE_1"]
    assert r.audit.generation is None  # legacy ablation field, not the runtime path


def test_audit_records_the_hash_pair_for_a_committed_patch(scene):
    s = sess(scene)
    start_mission(s, steps=CHAIN[:1])
    r = handle_turn(s, "FIRE_SITE_1 진압까지", MockBackend([resp_update("FIRE_SITE_1")]))
    a = r.audit
    assert len(a.patch_hash) == 64 and len(a.pre_state_hash) == 64
    assert a.pre_graph_hash != a.post_graph_hash
    assert a.pre_scene_hash == a.post_scene_hash  # graph moved, scene did not
    assert a.patch.accepted and a.patch.added_tasks
    assert a.state_changed and not a.scene_changed


def test_audit_records_plan_assignment_changes_as_a_plan_diff(scene):
    s = sess(scene)
    start_mission(s, steps=CHAIN[:1])
    r = handle_turn(s, "FIRE_SITE_1 진압까지", MockBackend([resp_update("FIRE_SITE_1")]))
    changes = r.audit.plan_assignment_changes
    assert set(changes.added) == {"GROUND_SUPPRESSION__FIRE_SITE_1"}
    assert changes.removed == {}


def test_audit_records_a_report_as_a_scene_change_only(scene):
    s = sess(scene)
    start_mission(s)
    r = handle_turn(
        s, "C 구역 화재", MockBackend([intent("REPORT_INCIDENT", zone_ref="C 구역")])
    )
    a = r.audit
    assert a.scene_changed and not a.state_changed
    assert a.pre_scene_hash != a.post_scene_hash
    assert a.pre_graph_hash == a.post_graph_hash
    assert a.patch is None and a.patch_hash is None


def test_audit_records_grounding_for_a_clarification(scene):
    s = sess(scene)
    start_mission(s)
    r = handle_turn(s, "그 화재 진압까지", MockBackend([resp_update("그 화재", deixis=True)]))
    g = r.audit.grounding
    assert g.status == "CLARIFICATION_REQUIRED"
    assert g.reason == "AMBIGUOUS_ENTITY"
    assert g.entity_id is None
    assert g.candidates == []  # S8: candidates are not offered for a mission-edit clarification


def test_plan_assignment_changes_classifies_added_removed_changed():
    d = PlanAssignmentChanges.between({"a": "S1", "b": "R1"}, {"b": "R2", "c": "G1"})
    assert d.added == {"c": "G1"}
    assert d.removed == {"a": "S1"}
    assert d.changed == {"b": ["R1", "R2"]}
    assert not d.empty
    assert PlanAssignmentChanges.between(None, None).empty


def test_execution_audit_schema_is_serializable():
    a = ExecutionAudit(
        session_id="S1",
        pre_scene_hash="a" * 64,
        pre_graph_hash="b" * 64,
        plan_assignments={"T": "S1"},
        execution_termination="COMPLETED",
        execution_assignments={"T": "S1"},
        makespan=12.5,
        capability_violations=[],
        precedence_violations=[],
        mode="mock",
        started_at="t0",
        finished_at="t1",
    )
    d = a.to_dict()
    assert d["event_type"] == "EXECUTION"
    assert d["execution_termination"] == "COMPLETED" and d["makespan"] == 12.5


# -- the session survives any failure in the turn (D-029) -----------------


def test_intent_classifier_exception_is_recorded_not_propagated(scene):
    class Boom:
        mode = "live"

        def complete(self, *a, **k):
            raise RuntimeError("network down")

    s = sess(scene)
    scene_before, state_before = s.scene, s.state
    r = handle_turn(s, "뭐든", Boom())

    assert r.outcome is TurnOutcome.TURN_ERROR
    assert "network down" in r.error
    assert r.audit.error_type == "RuntimeError"
    assert "network down" in r.audit.error_detail
    assert s.scene is scene_before and s.state is state_before
    assert s.turn_count == 1 and len(s.turn_log) == 1


def test_intent_schema_error_is_recorded_not_propagated(scene):
    s = sess(scene)
    r = handle_turn(s, "뭐든", MockBackend([{"intent": {"kind": "NOT_A_KIND"}}]))
    assert r.outcome is TurnOutcome.TURN_ERROR
    assert r.audit.error_type == "ValidationError"
    assert s.state is None and len(s.turn_log) == 1


def test_successful_live_intent_repair_is_explicit_in_the_turn_audit(scene):
    class RepairingLive:
        mode = "live"

        def __init__(self):
            self.calls = 0

        def complete(self, system, user, schema):
            self.calls += 1
            payload = wire_intent("QUERY_STATUS", about="agents").model_dump()
            if self.calls == 1:
                payload["note"] = "wrong slot"
            return schema.model_validate(payload)

    backend = RepairingLive()
    result = handle_turn(sess(scene), "로봇 상태", backend)

    assert result.outcome is TurnOutcome.ANSWERED
    assert result.audit.intent_repair_attempted
    assert result.audit.intent_repair_recovered
    assert backend.calls == 2


def test_failed_second_live_intent_wire_records_attempt_without_recovery(scene):
    class TwiceInvalid:
        mode = "live"

        def complete(self, system, user, schema):
            payload = new_mission().model_dump()
            payload["zone_ref"] = "Warehouse"
            return schema.model_validate(payload)

    result = handle_turn(sess(scene), "전체 정찰", TwiceInvalid())

    assert result.outcome is TurnOutcome.TURN_ERROR
    assert result.audit.intent_repair_attempted
    assert not result.audit.intent_repair_recovered
    assert result.audit.error_type == "ValidationError"


def test_compile_exception_is_recorded_not_propagated(scene, monkeypatch):
    from interaction import orchestrator

    monkeypatch.setattr(
        orchestrator,
        "compile_new_graph",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("compiler blew up")),
    )
    s = sess(scene)
    r = handle_turn(s, "임무 시작", MockBackend([new_mission()]))

    assert r.outcome is TurnOutcome.TURN_ERROR
    assert "compiler blew up" in r.audit.error_detail
    assert r.audit.intent_kind == "NEW_MISSION"
    assert s.state is None and s.plan is None
    assert s.turn_count == 1 and len(s.turn_log) == 1


# -- state and plan commit together (D-029) -------------------------------


def test_allocate_failure_on_new_mission_commits_nothing(scene, monkeypatch):
    from interaction import orchestrator

    s = sess(scene)
    monkeypatch.setattr(
        orchestrator, "allocate", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    r = handle_turn(s, "임무 시작", MockBackend([new_mission()]))

    assert r.outcome is TurnOutcome.TURN_ERROR
    assert s.state is None and s.plan is None            # no half-committed graph
    assert len(s.turn_log) == 1


def test_allocate_failure_on_update_keeps_the_previous_state_and_plan(scene, monkeypatch):
    from interaction import orchestrator

    s = sess(scene)
    start_mission(s, steps=CHAIN[:1])
    state_before, plan_before = s.state, s.plan

    monkeypatch.setattr(
        orchestrator, "allocate", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    r = handle_turn(s, "FIRE_SITE_1 진압까지", MockBackend([resp_update("FIRE_SITE_1")]))

    assert r.outcome is TurnOutcome.TURN_ERROR
    assert s.state is state_before and s.plan is plan_before
    assert len(s.state.graph) == 1                       # the patch did not land


# -- resolved_models covers the whole turn (§14, D-029) -------------------


class _ModelTrackingBackend(MockBackend):
    """MockBackend that reports a distinct resolved model per call."""

    def __init__(self, scripted):
        super().__init__(scripted)
        self.resolved_models: list[str] = []

    def complete(self, system, user, schema):
        self.resolved_models.append(f"model-{len(self.resolved_models) + 1}")
        return super().complete(system, user, schema)


def test_new_mission_is_a_single_llm_call(scene):
    # D-076: kind + Semantic Mission IR are one semantic-interpretation call.
    s = sess(scene)
    backend = _ModelTrackingBackend([new_mission()])
    r = handle_turn(s, "임무 시작", backend)

    assert r.outcome is TurnOutcome.COMMITTED
    assert backend.resolved_models == ["model-1"]
    assert r.audit.resolved_models == ["model-1"]
    assert [name for name, _ in r.audit.timing.llm_calls] == ["IntentWireEnvelope"]


def test_audit_model_list_is_per_turn_not_cumulative(scene):
    s = sess(scene)
    backend = _ModelTrackingBackend([new_mission(), intent("QUERY_STATUS")])
    handle_turn(s, "임무 시작", backend)
    r2 = handle_turn(s, "상태", backend)
    assert r2.audit.resolved_models == ["model-2"]


# -- QUERY details (D-029) -------------------------------------------------


def test_query_incidents_is_answerable_without_a_mission(scene):
    s = sess(scene)
    r = handle_turn(
        s, "어떤 화재가 있어?", MockBackend([intent("QUERY_STATUS", about="incidents")])
    )
    assert r.outcome is TurnOutcome.ANSWERED
    assert "FIRE_SITE_1" in r.message and "FIRE_SITE_2" in r.message
    assert "활성 임무가 없습니다" not in r.message


def _deictic_query(session):
    return handle_turn(
        session, "거기 상태", MockBackend([intent("QUERY_STATUS", target_phrase="거기")])
    )


def test_a_deictic_query_answers_without_refreshing_the_window(scene):
    s = sess(scene)
    s.note_referent("incident", "FIRE_SITE_1")
    introduced = s.recent_referents[0].introduced_turn

    for _ in range(2):  # inside the K=3 window
        r = _deictic_query(s)
        assert r.outcome is TurnOutcome.ANSWERED
        assert r.grounding.entity_id == "FIRE_SITE_1"
        assert r.grounding.via == ResolutionVia.REFERENT

    assert [(x.entity_id, x.introduced_turn) for x in s.recent_referents] == [
        ("FIRE_SITE_1", introduced)
    ]
    assert all(a.referent_noted is None for a in s.turn_log)


def test_repeated_deictic_queries_cannot_keep_a_referent_alive(scene):
    s = sess(scene)
    s.note_referent("incident", "FIRE_SITE_1")

    assert _deictic_query(s).outcome is TurnOutcome.ANSWERED   # turn 1
    assert _deictic_query(s).outcome is TurnOutcome.ANSWERED   # turn 2, last live turn
    expired = _deictic_query(s)                                # turn 3, out of window
    assert expired.outcome is TurnOutcome.CLARIFICATION
    assert expired.grounding.candidates == ("FIRE_SITE_1", "FIRE_SITE_2")


def test_an_explicit_query_does_refresh_the_window(scene):
    s = sess(scene)
    r = handle_turn(
        s, "FIRE_SITE_2 상태", MockBackend([intent("QUERY_STATUS", target_phrase="FIRE_SITE_2")])
    )
    assert r.audit.referent_noted == "FIRE_SITE_2"
    assert r.audit.grounding.via == "explicit"


def test_audit_records_how_a_referent_resolved(scene):
    s = sess(scene)
    start_mission(s)
    handle_turn(
        s, "A 구역 화재", MockBackend([intent("REPORT_INCIDENT", zone_ref="A 구역")])
    )
    r = handle_turn(s, "거기 진압까지", MockBackend([resp_update("거기", deixis=True)]))
    assert r.outcome is TurnOutcome.COMMITTED
    assert r.audit.semantic_ir.responses[0].targets == ["FIRE_SITE_3"]
    assert r.audit.referent_noted == "FIRE_SITE_3"


# -- backend provenance (§18.9, D-029) ------------------------------------


def test_mock_backend_and_its_subclasses_are_recorded_as_mock(scene):
    class ChildMock(MockBackend):
        pass

    s = sess(scene)
    r1 = handle_turn(s, "상태", MockBackend([intent("QUERY_STATUS")]))
    r2 = handle_turn(s, "상태", ChildMock([intent("QUERY_STATUS")]))
    assert r1.audit.mode == "mock" and r2.audit.mode == "mock"


def test_a_live_backend_is_recorded_as_live(scene):
    class LiveFake:
        mode = "live"

        def complete(self, system, user, schema):
            return intent("QUERY_STATUS")

    r = handle_turn(sess(scene), "상태", LiveFake())
    assert r.audit.mode == "live"


def test_a_cached_backend_is_recorded_as_cached(scene):
    class CachedFake:
        mode = "cached"

        def complete(self, system, user, schema):
            return intent("QUERY_STATUS")

    r = handle_turn(sess(scene), "상태", CachedFake())
    assert r.audit.mode == "cached"


@pytest.mark.parametrize("declared", [None, "LIVE", "fake", ""])
def test_a_backend_without_a_valid_mode_is_refused(scene, declared):
    ns = {"complete": lambda self, sy, u, sc: intent("QUERY_STATUS")}
    if declared is not None:
        ns["mode"] = declared
    Backend = type("Backend", (), ns)

    s = sess(scene)
    with pytest.raises(ValueError, match="mode"):
        handle_turn(s, "상태", Backend())
    assert s.turn_count == 0 and s.turn_log == ()
