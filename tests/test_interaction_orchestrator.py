"""P8.2 gate: the planning-session turn loop (§18.3, §18.4, §18.9, D-027/D-028).

The I1-I8 matrix from the P8 design, plus the invariants the orchestrator is
the single owner of. Everything runs headless on scripted MockBackend
responses — no network, no API key.
"""

from pathlib import Path

import pytest

from interaction.audit import ExecutionAudit, PlanAssignmentChanges, TurnAudit
from interaction.ground import ResolutionVia
from interaction.orchestrator import TurnOutcome, handle_turn
from interaction.schemas import IntentEnvelope
from interaction.session import MissionSession, SessionPhase
from llm.backend import MockBackend
from llm.schemas import LLMEdge, LLMTask, Step1Output, Step2Output
from scenarios.scene import load_scene

SCENE = Path(__file__).parents[1] / "scenarios" / "industrial_park.yaml"

CHAIN = ["THERMAL_RECON", "SUPPRESSANT_DROP", "GROUND_INSPECTION", "GROUND_SUPPRESSION"]


@pytest.fixture
def scene():
    return load_scene(SCENE)


def sess(scene, **kw) -> MissionSession:
    return MissionSession(session_id="S1", scene=scene, **kw)


def intent(kind: str, **slots) -> IntentEnvelope:
    return IntentEnvelope.model_validate({"intent": {"kind": kind, **slots}})


def mission_steps(incident_id: str, steps=CHAIN):
    """The Step1/Step2 pair generate_mission would need for one incident chain."""
    return [
        Step1Output(tasks=[LLMTask(task_type=s, target=incident_id) for s in steps]),
        Step2Output(
            edges=[
                LLMEdge(
                    predecessor=f"{a}:{incident_id}", successor=f"{b}:{incident_id}"
                )
                for a, b in zip(steps, steps[1:], strict=False)
            ]
        ),
    ]


def start_mission(session, incident_id="FIRE_SITE_1", steps=CHAIN):
    backend = MockBackend([intent("NEW_MISSION"), *mission_steps(incident_id, steps)])
    result = handle_turn(session, f"{incident_id} 대응 시작", backend)
    assert result.outcome is TurnOutcome.COMMITTED, result.message
    return result


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

    backend = MockBackend(
            [intent("UPDATE_MISSION", target_phrase="거기", up_to_step="GROUND_SUPPRESSION")]
        )
    r = handle_turn(s, "거기서 불이 난 곳을 꺼줘", backend)

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
    new_id = r1.grounding.entity_id and "FIRE_SITE_3"
    assert new_id in s.known_incident_ids
    assert r1.audit.scene_changed and not r1.audit.state_changed
    assert r1.audit.referent_noted == "FIRE_SITE_3"

    r2 = handle_turn(
        s,
        "거기부터 확인하고 불을 꺼줘",
        MockBackend(
            [intent("UPDATE_MISSION", target_phrase="거기", up_to_step="GROUND_SUPPRESSION")]
        ),
    )
    assert r2.outcome is TurnOutcome.COMMITTED
    assert r2.grounding.entity_id == "FIRE_SITE_3"  # the new one, not FIRE_SITE_1
    assert r2.patch_result.accepted
    assert [t.target for t in s.state.graph.tasks].count("FIRE_SITE_3") == 4
    # canonical extension releases nothing (D-006), observed not argued
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
    assert r.audit.answer and "THERMAL_RECON__FIRE_SITE_1" in r.audit.answer
    assert s.scene is scene_before and s.state is state_before
    assert s.plan is plan_before  # no re-allocation for a read
    assert not r.audit.state_changed and not r.audit.scene_changed


def test_query_before_any_mission_is_answered_not_an_error(scene):
    s = sess(scene)
    r = handle_turn(s, "지금 상황 어때?", MockBackend([intent("QUERY_STATUS")]))
    assert r.outcome is TurnOutcome.ANSWERED
    assert "활성 임무가 없습니다" in r.message
    assert s.state is None


# -- I4: two incidents, no referent --------------------------------------


def test_i4_ambiguous_referent_clarifies_with_candidates(scene):
    s = sess(scene)
    start_mission(s)
    state_before = s.state

    r = handle_turn(
        s,
        "그 화재부터 처리해줘",
        MockBackend(
            [intent("UPDATE_MISSION", target_phrase="그 화재", up_to_step="GROUND_SUPPRESSION")]
        ),
    )
    assert r.outcome is TurnOutcome.CLARIFICATION
    assert r.grounding.candidates == ("FIRE_SITE_1", "FIRE_SITE_2")
    assert s.state is state_before
    assert s.recent_referents == []


# -- I5: extending an existing chain -------------------------------------


def test_i5_extends_a_partial_chain(scene):
    s = sess(scene)
    start_mission(s, steps=CHAIN[:2])
    assert len(s.state.graph) == 2

    r = handle_turn(
        s,
        "FIRE_SITE_1 지상 진압까지 해줘",
        MockBackend(
            [intent("UPDATE_MISSION", target_phrase="FIRE_SITE_1", up_to_step="GROUND_SUPPRESSION")]
        ),
    )
    assert r.outcome is TurnOutcome.COMMITTED
    assert len(s.state.graph) == 4
    assert r.audit.patch.added_tasks == [
        "GROUND_INSPECTION__FIRE_SITE_1",
        "GROUND_SUPPRESSION__FIRE_SITE_1",
    ]


# -- I6: an update the Validator refuses ---------------------------------


def test_i6_rejected_patch_leaves_the_state_untouched(scene, monkeypatch):
    from core.enums import TaskType
    from interaction import orchestrator
    from interaction.ground import PatchPlan
    from validator.patch import AddEdge, MissionPatch

    s = sess(scene)
    start_mission(s, steps=CHAIN[:1])
    state_before, plan_before = s.state, s.plan

    # A cross-incident edge is exactly what the canonical builder never emits,
    # so force one in to prove the orchestrator does not commit a rejection.
    def cross_incident(graph, incident_id, up_to_step):
        return PatchPlan(
            patch=MissionPatch(
                [
                    AddEdge(
                        (TaskType.THERMAL_RECON, "FIRE_SITE_1"),
                        (TaskType.THERMAL_RECON, "FIRE_SITE_2"),
                    )
                ]
            ),
            note="forced",
        )

    monkeypatch.setattr(orchestrator, "build_chain_patch", cross_incident)
    r = handle_turn(
        s,
        "FIRE_SITE_1 진압까지",
        MockBackend(
            [intent("UPDATE_MISSION", target_phrase="FIRE_SITE_1", up_to_step="GROUND_SUPPRESSION")]
        ),
    )

    assert r.outcome is TurnOutcome.REJECTED
    assert not r.patch_result.accepted
    assert s.state is state_before and s.plan is plan_before
    assert s.recent_referents == []  # a failed UPDATE adds no referent (§18.5)
    assert r.audit.patch_hash and r.audit.pre_state_hash  # audit pair still recorded


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
        s,
        "FIRE_SITE_1 다시 지상 진압까지 처리해줘",
        MockBackend(
            [intent("UPDATE_MISSION", target_phrase="FIRE_SITE_1", up_to_step="GROUND_SUPPRESSION")]
        ),
    )
    assert r.outcome is TurnOutcome.NO_CHANGE
    assert "이미 계획에 포함" in r.message
    assert s.state is state_before and s.plan is plan_before
    assert r.patch_result is None  # no patch was even attempted
    assert not r.audit.state_changed


def test_no_change_still_keeps_the_referent_for_the_next_turn(scene):
    # §18.5: the UPDATE grounded correctly; only failures drop the referent.
    s = sess(scene)
    start_mission(s)
    handle_turn(
        s,
        "FIRE_SITE_1 진압까지",
        MockBackend(
            [intent("UPDATE_MISSION", target_phrase="FIRE_SITE_1", up_to_step="GROUND_SUPPRESSION")]
        ),
    )
    assert s.recent_referents[-1].entity_id == "FIRE_SITE_1"

    r = handle_turn(
        s,
        "거기 상태 알려줘",
        MockBackend([intent("QUERY_STATUS", target_phrase="거기")]),
    )
    assert r.outcome is TurnOutcome.ANSWERED
    assert r.grounding.entity_id == "FIRE_SITE_1"


def test_a_lower_step_request_is_no_change_not_a_shrink(scene):
    s = sess(scene)
    start_mission(s)
    before = len(s.state.graph)
    r = handle_turn(
        s,
        "FIRE_SITE_1은 확인만 해",
        MockBackend(
            [intent("UPDATE_MISSION", target_phrase="FIRE_SITE_1", up_to_step="THERMAL_RECON")]
        ),
    )
    assert r.outcome is TurnOutcome.NO_CHANGE
    assert len(s.state.graph) == before


# -- lifecycle (§18.4) ----------------------------------------------------


def test_new_mission_when_one_exists_does_not_replace_it(scene):
    s = sess(scene)
    start_mission(s)
    state_before = s.state
    r = handle_turn(s, "처음부터 다시 만들어줘", MockBackend([intent("NEW_MISSION")]))
    assert r.outcome is TurnOutcome.CLARIFICATION
    assert s.state is state_before


def test_update_without_a_mission_clarifies(scene):
    s = sess(scene)
    r = handle_turn(
        s,
        "FIRE_SITE_1 진압까지",
        MockBackend(
            [intent("UPDATE_MISSION", target_phrase="FIRE_SITE_1", up_to_step="GROUND_SUPPRESSION")]
        ),
    )
    assert r.outcome is TurnOutcome.CLARIFICATION
    assert "활성 임무가 없습니다" in r.message
    assert s.state is None


def test_missing_step_slot_clarifies(scene):
    s = sess(scene)
    start_mission(s, steps=CHAIN[:1])
    state_before = s.state
    r = handle_turn(
        s,
        "FIRE_SITE_1 처리해줘",
        MockBackend([intent("UPDATE_MISSION", target_phrase="FIRE_SITE_1")]),
    )
    assert r.outcome is TurnOutcome.CLARIFICATION
    assert "어느 단계까지" in r.message
    assert s.state is state_before


@pytest.mark.parametrize("kind", ["NEW_MISSION", "REPORT_INCIDENT", "UPDATE_MISSION"])
@pytest.mark.parametrize("phase", [SessionPhase.EXECUTED, SessionPhase.EXECUTION_FAILED])
def test_planning_acts_are_unsupported_after_execution(scene, kind, phase):
    s = sess(scene, phase=phase)
    scene_before, state_before = s.scene, s.state
    slots = {"zone_ref": "A"} if kind == "REPORT_INCIDENT" else {}
    if kind == "UPDATE_MISSION":
        slots = {"target_phrase": "FIRE_SITE_1", "up_to_step": "THERMAL_RECON"}
    r = handle_turn(s, "뭔가 해줘", MockBackend([intent(kind, **slots)]))
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
    ("kind", "slots"),
    [
        ("UNSUPPORTED", {}),
        ("QUERY_STATUS", {}),
        ("UPDATE_MISSION", {"target_phrase": "그 화재", "up_to_step": "THERMAL_RECON"}),
        ("REPORT_INCIDENT", {"zone_ref": "없는구역"}),
    ],
)
def test_no_referent_is_added_on_a_non_grounded_turn(scene, kind, slots):
    s = sess(scene)
    start_mission(s)
    before = list(s.recent_referents)
    handle_turn(s, "...", MockBackend([intent(kind, **slots)]))
    assert s.recent_referents == before


def test_referents_only_ever_come_from_the_orchestrator(scene):
    # Every id in recent_referents must exist in the scene — note_referent is
    # the only writer and it validates membership (P8.1a).
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
        s,
        "FIRE_SITE_1 확인만",
        MockBackend(
            [intent("UPDATE_MISSION", target_phrase="FIRE_SITE_1", up_to_step="THERMAL_RECON")]
        ),
    )
    assert len(calls) == 1                                    # NO_CHANGE

    handle_turn(
        s,
        "FIRE_SITE_1 진압까지",
        MockBackend(
            [intent("UPDATE_MISSION", target_phrase="FIRE_SITE_1", up_to_step="GROUND_SUPPRESSION")]
        ),
    )
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


def test_audit_records_the_hash_pair_for_a_committed_patch(scene):
    s = sess(scene)
    start_mission(s, steps=CHAIN[:1])
    r = handle_turn(
        s,
        "FIRE_SITE_1 진압까지",
        MockBackend(
            [intent("UPDATE_MISSION", target_phrase="FIRE_SITE_1", up_to_step="GROUND_SUPPRESSION")]
        ),
    )
    a = r.audit
    assert len(a.patch_hash) == 64 and len(a.pre_state_hash) == 64
    assert a.pre_graph_hash != a.post_graph_hash
    assert a.pre_scene_hash == a.post_scene_hash  # graph moved, scene did not
    assert a.patch.accepted and a.patch.added_tasks
    assert a.state_changed and not a.scene_changed


def test_audit_records_plan_assignment_changes_as_a_plan_diff(scene):
    s = sess(scene)
    start_mission(s, steps=CHAIN[:1])
    r = handle_turn(
        s,
        "FIRE_SITE_1 진압까지",
        MockBackend(
            [intent("UPDATE_MISSION", target_phrase="FIRE_SITE_1", up_to_step="GROUND_SUPPRESSION")]
        ),
    )
    changes = r.audit.plan_assignment_changes
    assert set(changes.added) == {
        "SUPPRESSANT_DROP__FIRE_SITE_1",
        "GROUND_INSPECTION__FIRE_SITE_1",
        "GROUND_SUPPRESSION__FIRE_SITE_1",
    }
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
    r = handle_turn(
        s,
        "그 화재 진압까지",
        MockBackend(
            [intent("UPDATE_MISSION", target_phrase="그 화재", up_to_step="GROUND_SUPPRESSION")]
        ),
    )
    g = r.audit.grounding
    assert g.status == "CLARIFICATION_REQUIRED"
    assert g.candidates == ["FIRE_SITE_1", "FIRE_SITE_2"]
    assert g.entity_id is None


def test_plan_assignment_changes_classifies_added_removed_changed():
    d = PlanAssignmentChanges.between({"a": "S1", "b": "R1"}, {"b": "R2", "c": "G1"})
    assert d.added == {"c": "G1"}
    assert d.removed == {"a": "S1"}
    assert d.changed == {"b": ["R1", "R2"]}
    assert not d.empty
    assert PlanAssignmentChanges.between(None, None).empty


def test_execution_audit_schema_is_serializable():
    # Producer arrives with the execute action in P8.3; pin the shape now.
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
    assert r.audit.error_type == "RuntimeError"          # kept in the record
    assert "network down" in r.audit.error_detail
    assert s.scene is scene_before and s.state is state_before
    assert s.turn_count == 1 and len(s.turn_log) == 1


def test_intent_schema_error_is_recorded_not_propagated(scene):
    s = sess(scene)
    r = handle_turn(s, "뭐든", MockBackend([{"intent": {"kind": "NOT_A_KIND"}}]))
    assert r.outcome is TurnOutcome.TURN_ERROR
    assert r.audit.error_type == "ValidationError"
    assert s.state is None and len(s.turn_log) == 1


def test_mission_step_exception_is_recorded_not_propagated(scene):
    # The old try/except only wrapped the intent call, so a backend that died
    # in generate_mission's Step1/Step2/repair escaped handle_turn entirely.
    class BoomAfterIntent:
        mode = "live"

        def __init__(self):
            self.calls = 0

        def complete(self, system, user, schema):
            self.calls += 1
            if self.calls == 1:
                return intent("NEW_MISSION")
            raise RuntimeError("network down mid-mission")

    s = sess(scene)
    r = handle_turn(s, "임무 시작", BoomAfterIntent())

    assert r.outcome is TurnOutcome.TURN_ERROR
    assert "network down mid-mission" in r.audit.error_detail
    assert r.audit.intent_kind == "NEW_MISSION"          # classification did happen
    assert s.state is None and s.plan is None
    assert s.turn_count == 1 and len(s.turn_log) == 1


def test_mission_backend_running_dry_is_recorded_not_propagated(scene):
    s = sess(scene)
    r = handle_turn(s, "임무 시작", MockBackend([intent("NEW_MISSION")]))  # no Step1
    assert r.outcome is TurnOutcome.TURN_ERROR
    assert r.audit.error_type == "AssertionError"
    assert s.state is None and len(s.turn_log) == 1


def test_mission_schema_error_is_a_rejection_not_a_turn_error(scene):
    # Distinct meaning from a transport failure: the model answered, the answer
    # was invalid, and P5 turns that into an explicit REJECTED (§12, D-019).
    s = sess(scene)
    bad_step1 = {"tasks": [{"task_type": "AREA_RECON", "target": "ZONE_A", "position": [1, 2]}]}
    r = handle_turn(s, "임무 시작", MockBackend([intent("NEW_MISSION"), bad_step1]))

    assert r.outcome is TurnOutcome.REJECTED
    assert r.audit.error_type is None                    # not an error, a verdict
    assert r.audit.generation is not None
    assert not r.audit.generation.approved
    assert r.audit.generation.failure_category == "SCHEMA"
    assert s.state is None


# -- state and plan commit together (D-029) -------------------------------


def test_allocate_failure_on_new_mission_commits_nothing(scene, monkeypatch):
    from interaction import orchestrator

    s = sess(scene)
    monkeypatch.setattr(
        orchestrator, "allocate", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    r = handle_turn(
        s, "임무 시작", MockBackend([intent("NEW_MISSION"), *mission_steps("FIRE_SITE_1")])
    )

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
    r = handle_turn(
        s,
        "FIRE_SITE_1 진압까지",
        MockBackend(
            [intent("UPDATE_MISSION", target_phrase="FIRE_SITE_1", up_to_step="GROUND_SUPPRESSION")]
        ),
    )

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


def test_audit_records_every_backend_call_of_the_turn(scene):
    # NEW_MISSION is one intent call plus generate_mission's Step1 and Step2.
    s = sess(scene)
    backend = _ModelTrackingBackend([intent("NEW_MISSION"), *mission_steps("FIRE_SITE_1")])
    r = handle_turn(s, "임무 시작", backend)

    assert r.outcome is TurnOutcome.COMMITTED
    assert backend.resolved_models == ["model-1", "model-2", "model-3"]
    assert r.audit.resolved_models == backend.resolved_models


def test_audit_model_list_is_per_turn_not_cumulative(scene):
    s = sess(scene)
    backend = _ModelTrackingBackend(
        [intent("NEW_MISSION"), *mission_steps("FIRE_SITE_1"), intent("QUERY_STATUS")]
    )
    handle_turn(s, "임무 시작", backend)
    r2 = handle_turn(s, "상태", backend)
    assert r2.audit.resolved_models == ["model-4"]


# -- QUERY details (D-029) -------------------------------------------------


def test_query_incidents_is_answerable_without_a_mission(scene):
    # Incidents live in the scene, not the mission.
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
    # §18.5/D-029: a read is not a new act of reference, so introduced_turn
    # must stay put.
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
    # The bug this replaced: every read re-noted the referent, so K=3 never
    # expired as long as the operator kept asking.
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
    r = handle_turn(
        s,
        "거기 진압까지",
        MockBackend(
            [intent("UPDATE_MISSION", target_phrase="거기", up_to_step="GROUND_SUPPRESSION")]
        ),
    )
    assert r.audit.grounding.via == "referent"
    assert r.audit.grounding.entity_kind == "incident"


# -- backend provenance (§18.9, D-029) ------------------------------------


def test_mock_backend_and_its_subclasses_are_recorded_as_mock(scene):
    class ChildMock(MockBackend):
        pass

    s = sess(scene)
    r1 = handle_turn(s, "상태", MockBackend([intent("QUERY_STATUS")]))
    r2 = handle_turn(s, "상태", ChildMock([intent("QUERY_STATUS")]))
    # a class-name comparison reported the subclass as live, which the contract
    # forbids: cached and mocked answers must never be presented as live.
    assert r1.audit.mode == "mock" and r2.audit.mode == "mock"


def test_a_live_backend_is_recorded_as_live(scene):
    class LiveFake:
        mode = "live"

        def complete(self, system, user, schema):
            return intent("QUERY_STATUS")

    r = handle_turn(sess(scene), "상태", LiveFake())
    assert r.audit.mode == "live"


def test_a_cached_backend_is_recorded_as_cached(scene):
    # P8.3 will add a real one; the mode plumbing already carries it.
    class CachedFake:
        mode = "cached"

        def complete(self, system, user, schema):
            return intent("QUERY_STATUS")

    r = handle_turn(sess(scene), "상태", CachedFake())
    assert r.audit.mode == "cached"


@pytest.mark.parametrize("declared", [None, "LIVE", "fake", ""])
def test_a_backend_without_a_valid_mode_is_refused(scene, declared):
    # A wiring bug, not a turn failure: mislabelling provenance is worse than
    # stopping, so this raises instead of defaulting to "live".
    ns = {"complete": lambda self, sy, u, sc: intent("QUERY_STATUS")}
    if declared is not None:
        ns["mode"] = declared
    Backend = type("Backend", (), ns)

    s = sess(scene)
    with pytest.raises(ValueError, match="mode"):
        handle_turn(s, "상태", Backend())
    # the refused turn never happened: no turn id burned, no audit record
    assert s.turn_count == 0 and s.turn_log == []
