"""D-076: operator intent schemas — dialogue act + Semantic Mission IR.

The classifier's job in one structured-output call: pick one of six kinds and,
for ``NEW_MISSION`` / ``UPDATE_MISSION`` only, emit a ``SemanticMissionIR`` of
generic language operators. It never emits task/edge lists, ids, coordinates,
priority, an assignment, a MissionPatch or a clarification. These tests pin the
wire shape, the S1 cross-field rule (mission ⇔ mission-editing act), the
resource slots (P13) and the deterministic wire→internal conversion.

The Semantic Mission IR schema itself is tests/test_mission_ir.py; resolution
against a live world is tests/test_resolve.py.
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from interaction.interpret import IntentRepairTrace, classify
from interaction.resources import CountConstraint, ResourceRequest
from interaction.schemas import (
    IntentEnvelope,
    IntentWireEnvelope,
    NewMissionIntent,
    QueryStatusIntent,
    ReportIncidentIntent,
    UnsupportedIntent,
    UpdateMissionIntent,
    UpdateResourcesIntent,
    wire_intent,
)
from interaction.session import MissionSession
from llm.backend import MockBackend
from scenarios.scene import load_scene
from tests.ir_fixtures import mission_ir, recon, response

SCENE = Path(__file__).parents[1] / "scenarios" / "industrial_park.yaml"

_WIRE_NULLS = {
    "kind": None,
    "mission": None,
    "zone_ref": None,
    "target_phrase": None,
    "response_up_to": None,
    "about": None,
    "note": None,
    "uav_exact": None,
    "uav_min": None,
    "uav_max": None,
    "ugv_exact": None,
    "ugv_min": None,
    "ugv_max": None,
    "required_agents": None,
    "excluded_agents": None,
}


def _wire_payload(kind: str = "NEW_MISSION", **changes) -> dict:
    """Raw (unvalidated) wire dict — for feeding a backend directly."""
    payload = dict(_WIRE_NULLS)
    payload["kind"] = kind
    payload.update(changes)
    return payload


def _recon_ir(**zone_kw):
    return mission_ir(recon=(recon(**zone_kw),))


def _envelope(payload: dict) -> IntentEnvelope:
    return IntentEnvelope.model_validate({"intent": payload})


# -- the internal intent models -----------------------------------------


def test_new_and_update_mission_carry_a_semantic_mission_ir():
    ir = _recon_ir(range_from="A", range_to="C")
    new = _envelope({"kind": "NEW_MISSION", "mission": ir}).intent
    assert isinstance(new, NewMissionIntent)
    assert new.mission.recon[0].zones.range_from == "A"
    assert new.resources is None

    upd = _envelope({"kind": "UPDATE_MISSION", "mission": ir}).intent
    assert isinstance(upd, UpdateMissionIntent)
    assert upd.mission is ir


def test_new_mission_may_not_carry_a_graph_or_a_patch():
    # D-076: the classifier emits operators only; no task/edge lists, no ops.
    with pytest.raises(ValidationError):
        _envelope(
            {
                "kind": "NEW_MISSION",
                "mission": _recon_ir(explicit=("A",)),
                "tasks": [{"task_type": "AREA_RECON"}],
            }
        )


def test_report_incident_keeps_its_zone_and_response_slots():
    assert _envelope({"kind": "REPORT_INCIDENT"}).intent.zone_ref is None
    got = _envelope({"kind": "REPORT_INCIDENT", "zone_ref": "A 구역"}).intent
    assert isinstance(got, ReportIncidentIntent) and got.zone_ref == "A 구역"
    response_ = _envelope(
        {
            "kind": "REPORT_INCIDENT",
            "zone_ref": "Warehouse",
            "response_up_to": "GROUND_INSPECTION",
        }
    ).intent
    assert response_.response_up_to == "GROUND_INSPECTION"


@pytest.mark.parametrize("extra", [{"label": "북쪽 화재"}, {"urgent": True}, {"priority": 9}])
def test_report_incident_rejects_removed_slots(extra):
    with pytest.raises(ValidationError):
        _envelope({"kind": "REPORT_INCIDENT", "zone_ref": "ZONE_A", **extra})


def test_query_status_defaults_to_mission_and_takes_a_referent():
    bare = _envelope({"kind": "QUERY_STATUS"}).intent
    assert isinstance(bare, QueryStatusIntent)
    assert bare.about == "mission" and bare.target_phrase is None

    got = _envelope(
        {"kind": "QUERY_STATUS", "about": "agents", "target_phrase": "그 화재"}
    ).intent
    assert got.about == "agents" and got.target_phrase == "그 화재"


def test_unsupported_carries_an_audit_note():
    got = _envelope({"kind": "UNSUPPORTED", "note": "asked to cancel a task"}).intent
    assert isinstance(got, UnsupportedIntent) and got.note


# -- the classifier must not produce a clarification (§18.7) -------------


def test_clarification_is_not_a_classifier_output():
    with pytest.raises(ValidationError):
        _envelope({"kind": "CLARIFICATION_REQUIRED", "question": "어느 화재입니까?"})


def test_unknown_kind_is_rejected():
    with pytest.raises(ValidationError):
        _envelope({"kind": "CANCEL_TASK"})


def test_missing_kind_is_rejected():
    with pytest.raises(ValidationError):
        _envelope({"target_phrase": "거기"})


# -- wire shape: one flat object, OpenAI-strict ------------------------


def test_wire_schema_has_no_openai_rejected_one_of_and_requires_every_key():
    schema = IntentWireEnvelope.model_json_schema()
    assert '"oneOf"' not in json.dumps(schema)
    assert set(schema["required"]) == set(schema["properties"])
    assert set(schema["properties"]) == {
        "kind",
        "mission",
        "zone_ref",
        "target_phrase",
        "response_up_to",
        "about",
        "note",
        "uav_exact",
        "uav_min",
        "uav_max",
        "ugv_exact",
        "ugv_min",
        "ugv_max",
        "required_agents",
        "excluded_agents",
    }


def test_wire_openai_strict_json_schema_has_no_defaults():
    from openai.lib._pydantic import to_strict_json_schema

    text = json.dumps(to_strict_json_schema(IntentWireEnvelope))
    assert '"default"' not in text
    assert '"oneOf"' not in text


def test_wire_requires_explicit_nulls_and_strict_types():
    payload = _wire_payload("QUERY_STATUS")
    payload.pop("note")
    with pytest.raises(ValidationError):
        IntentWireEnvelope.model_validate(payload)

    payload = _wire_payload("REPORT_INCIDENT", zone_ref=123)
    with pytest.raises(ValidationError):
        IntentWireEnvelope.model_validate(payload)


def test_wire_rejects_coerced_and_wrong_case_literals():
    with pytest.raises(ValidationError):
        IntentWireEnvelope.model_validate(_wire_payload("QUERY_STATUS", about="AGENTS"))


# -- S1: mission ⇔ mission-editing act --------------------------------


@pytest.mark.parametrize("kind", ["NEW_MISSION", "UPDATE_MISSION"])
def test_mission_editing_act_requires_a_mission(kind):
    with pytest.raises(ValidationError, match="requires a mission"):
        IntentWireEnvelope.model_validate(_wire_payload(kind))


@pytest.mark.parametrize(
    "kind", ["REPORT_INCIDENT", "UPDATE_RESOURCES", "QUERY_STATUS", "UNSUPPORTED"]
)
def test_non_mission_act_may_not_carry_a_mission(kind):
    payload = _wire_payload(kind, mission=_recon_ir(explicit=("A",)))
    if kind == "UPDATE_RESOURCES":
        payload["uav_exact"] = 1
    if kind == "UNSUPPORTED":
        payload["note"] = "x"
    with pytest.raises(ValidationError, match="cannot carry a mission"):
        IntentWireEnvelope.model_validate(payload)


@pytest.mark.parametrize(
    ("kind", "irrelevant"),
    [
        ("NEW_MISSION", {"zone_ref": "ZONE_A"}),
        ("NEW_MISSION", {"response_up_to": "GROUND_SUPPRESSION"}),
        ("UPDATE_MISSION", {"about": "mission"}),
        ("UPDATE_MISSION", {"uav_exact": 1}),
        ("REPORT_INCIDENT", {"target_phrase": "거기"}),
        ("UPDATE_RESOURCES", {"target_phrase": "거기"}),
        ("QUERY_STATUS", {"note": "x"}),
        ("UNSUPPORTED", {"zone_ref": "ZONE_A"}),
    ],
)
def test_wire_rejects_non_null_slots_owned_by_another_kind(kind, irrelevant):
    payload = _wire_payload(kind, **irrelevant)
    if kind in {"NEW_MISSION", "UPDATE_MISSION"}:
        payload["mission"] = _recon_ir(explicit=("A",))
    if kind == "UNSUPPORTED":
        payload["note"] = payload["note"] or "x"
    with pytest.raises(ValidationError, match="cannot populate slots"):
        IntentWireEnvelope.model_validate(payload)


# -- wire → internal discriminated union -------------------------------


def test_wire_converts_new_mission_with_its_ir_and_resources():
    ir = mission_ir(
        recon=(recon(range_from="A", range_to="D", exclude=("B",)),),
        responses=(response("GROUND_SUPPRESSION", explicit=("FIRE_SITE_1",)),),
    )
    wire = wire_intent(
        "NEW_MISSION", mission=ir, uav_exact=1, ugv_min=1, ugv_max=2,
        required_agents=["G1"], excluded_agents=["R2"],
    )
    intent = wire.to_internal().intent
    assert isinstance(intent, NewMissionIntent)
    assert intent.mission.recon[0].zones.exclude == ["B"]
    assert intent.mission.responses[0].response_up_to == "GROUND_SUPPRESSION"

    request = intent.resources.to_domain()
    assert request.uav.exact == 1
    assert request.ugv.minimum == 1 and request.ugv.maximum == 2
    assert request.required_agents == ("G1",)
    assert request.excluded_agents == ("R2",)


def test_wire_converts_update_mission_carrying_only_the_ir():
    ir = _recon_ir(region="WEST")
    intent = wire_intent("UPDATE_MISSION", mission=ir).to_internal().intent
    assert isinstance(intent, UpdateMissionIntent)
    assert intent.mission.recon[0].zones.region == "WEST"


@pytest.mark.parametrize(
    ("wire", "expected_type", "expected"),
    [
        (
            wire_intent(
                "REPORT_INCIDENT",
                zone_ref="A 구역",
                response_up_to="GROUND_INSPECTION",
                uav_exact=1,
            ),
            ReportIncidentIntent,
            {"zone_ref": "A 구역", "response_up_to": "GROUND_INSPECTION"},
        ),
        (
            wire_intent("UPDATE_RESOURCES", uav_exact=1, excluded_agents=["R2"]),
            UpdateResourcesIntent,
            {},
        ),
        (
            wire_intent("QUERY_STATUS", about="agents", target_phrase="그 화재"),
            QueryStatusIntent,
            {"about": "agents", "target_phrase": "그 화재"},
        ),
        (
            wire_intent("UNSUPPORTED", note="outside scope"),
            UnsupportedIntent,
            {"note": "outside scope"},
        ),
    ],
)
def test_wire_converts_the_non_mission_acts(wire, expected_type, expected):
    internal = wire.to_internal().intent
    assert isinstance(internal, expected_type)
    for key, value in expected.items():
        assert getattr(internal, key) == value


def test_resource_update_and_report_restore_strict_requests():
    update = (
        wire_intent("UPDATE_RESOURCES", uav_min=1, uav_max=2, excluded_agents=["R2"])
        .to_internal()
        .intent
    )
    report = (
        wire_intent("REPORT_INCIDENT", zone_ref="Warehouse", ugv_exact=1)
        .to_internal()
        .intent
    )
    assert update.resources.to_domain() == ResourceRequest(
        uav=CountConstraint(minimum=1, maximum=2),
        excluded_agents=("R2",),
    )
    assert report.resources.to_domain() == ResourceRequest(ugv=CountConstraint(exact=1))


@pytest.mark.parametrize(
    "slots",
    [
        {"uav_exact": True},
        {"uav_exact": "1"},
        {"uav_exact": 1, "uav_min": 1},
        {"uav_min": 2, "uav_max": 1},
        {"required_agents": ["G1", "G1"]},
        {"required_agents": ["G1"], "excluded_agents": ["G1"]},
    ],
)
def test_wire_rejects_invalid_resource_constraints(slots):
    with pytest.raises(ValidationError):
        wire_intent("REPORT_INCIDENT", zone_ref="Warehouse", **slots)


# -- D-052 transport: one bounded wire repair, live/cached only ---------


class _RepairBackend:
    def __init__(self, mode, responses):
        self.mode = mode
        self.responses = iter(responses)
        self.calls = []

    def complete(self, system, user, schema):
        self.calls.append((system, user, schema.__name__))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return schema.model_validate(response)


def test_classifier_requests_wire_schema_then_returns_internal_intent():
    backend = MockBackend([wire_intent("QUERY_STATUS", about="agents")])
    session = MissionSession("WIRE", load_scene(SCENE))

    result = classify(session, "로봇 상태", backend)

    assert isinstance(result, QueryStatusIntent)
    assert result.about == "agents"
    assert backend.calls[0][2] == "IntentWireEnvelope"


@pytest.mark.parametrize("mode", ["live", "cached"])
def test_live_and_cached_intent_wire_get_exactly_one_strict_schema_repair(mode):
    invalid = _wire_payload("NEW_MISSION", note="전체 구역 순찰")
    valid = _wire_payload(
        "NEW_MISSION", mission=_recon_ir(explicit=("A",)).model_dump()
    )
    backend = _RepairBackend(mode, [invalid, valid])
    session = MissionSession("REPAIR", load_scene(SCENE))
    trace = IntentRepairTrace()

    result = classify(session, "A 구역 정찰해줘", backend, repair_trace=trace)

    assert isinstance(result, NewMissionIntent)
    assert result.mission.recon[0].zones.explicit == ["A"]
    assert len(backend.calls) == 2
    assert backend.calls[0][1:] == backend.calls[1][1:]
    assert "previous JSON response was rejected" in backend.calls[1][0]
    assert "cannot populate slots" in backend.calls[1][0]
    assert trace.attempted and trace.recovered


def test_second_invalid_live_wire_is_not_repaired_again():
    invalid = _wire_payload("NEW_MISSION", zone_ref="Warehouse")
    backend = _RepairBackend("live", [invalid, invalid])
    session = MissionSession("REPAIR2", load_scene(SCENE))
    trace = IntentRepairTrace()

    with pytest.raises(ValidationError, match="cannot populate slots"):
        classify(session, "전체 구역 순찰", backend, repair_trace=trace)
    assert len(backend.calls) == 2
    assert trace.attempted and not trace.recovered


def test_non_schema_backend_failure_is_never_retried():
    backend = _RepairBackend("live", [RuntimeError("network down")])
    session = MissionSession("NO-RETRY", load_scene(SCENE))

    with pytest.raises(RuntimeError, match="network down"):
        classify(session, "전체 구역 순찰", backend)
    assert len(backend.calls) == 1


def test_mock_schema_failure_is_not_hidden_by_repair():
    invalid = _wire_payload("NEW_MISSION", note="bad mock script")
    backend = _RepairBackend("mock", [invalid, _wire_payload("QUERY_STATUS")])
    session = MissionSession("MOCK-NO-REPAIR", load_scene(SCENE))

    with pytest.raises(ValidationError, match="cannot populate slots"):
        classify(session, "전체 구역 순찰", backend)
    assert len(backend.calls) == 1
