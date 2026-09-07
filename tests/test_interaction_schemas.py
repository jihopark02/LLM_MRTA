"""P8.1a: operator intent schemas (RESEARCH_CONTRACT.md §18.2, §18.7, D-027).

The classifier's job is narrow by construction: five kinds, slots only, no
clarification member, no task generation. These tests pin the D-027 removals
(`tasks`, `label`, `urgent`, `priority`) at the schema level.
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from interaction.interpret import classify
from interaction.prompts import intent_system
from interaction.schemas import (
    IntentEnvelope,
    IntentWireEnvelope,
    NewMissionIntent,
    QueryStatusIntent,
    ReportIncidentIntent,
    UnsupportedIntent,
    UpdateMissionIntent,
    wire_intent,
)
from interaction.session import MissionSession
from llm.backend import MockBackend
from scenarios.scene import load_scene

SCENE = Path(__file__).parents[1] / "scenarios" / "industrial_park.yaml"


def _envelope(payload: dict) -> IntentEnvelope:
    return IntentEnvelope.model_validate({"intent": payload})


# -- the five supported kinds parse ---------------------------------


def test_new_mission_has_only_the_optional_incident_policy_slot():
    e = _envelope({"kind": "NEW_MISSION"})
    assert isinstance(e.intent, NewMissionIntent)
    assert e.intent.incident_response_up_to is None
    policy = _envelope(
        {"kind": "NEW_MISSION", "incident_response_up_to": "GROUND_SUPPRESSION"}
    ).intent
    assert policy.incident_response_up_to == "GROUND_SUPPRESSION"


def test_report_incident_zone_ref_optional():
    assert _envelope({"kind": "REPORT_INCIDENT"}).intent.zone_ref is None
    got = _envelope({"kind": "REPORT_INCIDENT", "zone_ref": "A 구역"}).intent
    assert isinstance(got, ReportIncidentIntent) and got.zone_ref == "A 구역"
    response = _envelope(
        {
            "kind": "REPORT_INCIDENT",
            "zone_ref": "Warehouse",
            "response_up_to": "GROUND_INSPECTION",
        }
    ).intent
    assert response.response_up_to == "GROUND_INSPECTION"


def test_update_mission_slots_are_optional():
    bare = _envelope({"kind": "UPDATE_MISSION"}).intent
    assert isinstance(bare, UpdateMissionIntent)
    assert bare.target_phrase is None and bare.up_to_step is None

    full = _envelope(
        {"kind": "UPDATE_MISSION", "target_phrase": "거기", "up_to_step": "GROUND_SUPPRESSION"}
    ).intent
    assert full.target_phrase == "거기" and full.up_to_step == "GROUND_SUPPRESSION"


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


# -- the classifier must not produce a clarification (§18.7) ---------


def test_clarification_is_not_a_classifier_output():
    # CLARIFICATION_REQUIRED is the deterministic grounder's verdict, never the
    # model's — there is no such member in the union.
    with pytest.raises(ValidationError):
        _envelope({"kind": "CLARIFICATION_REQUIRED", "question": "어느 화재입니까?"})


def test_unknown_kind_is_rejected():
    with pytest.raises(ValidationError):
        _envelope({"kind": "CANCEL_TASK"})


def test_missing_kind_is_rejected():
    with pytest.raises(ValidationError):
        _envelope({"target_phrase": "거기"})


# -- D-027 removals are enforced by the schema ----------------------


def test_new_mission_may_not_carry_tasks():
    # D-027: the classifier does not decompose; generate_mission does (§12).
    with pytest.raises(ValidationError):
        _envelope({"kind": "NEW_MISSION", "tasks": [{"task_type": "AREA_RECON"}]})


@pytest.mark.parametrize("extra", [{"label": "북쪽 화재"}, {"urgent": True}, {"priority": 9}])
def test_report_incident_rejects_removed_slots(extra):
    with pytest.raises(ValidationError):
        _envelope({"kind": "REPORT_INCIDENT", "zone_ref": "ZONE_A", **extra})


def test_update_rejects_agent_or_task_id_slots():
    with pytest.raises(ValidationError):
        _envelope({"kind": "UPDATE_MISSION", "target_phrase": "거기", "agent": "G1"})
    with pytest.raises(ValidationError):
        _envelope(
            {"kind": "UPDATE_MISSION", "task_id": "GROUND_SUPPRESSION__FIRE_SITE_1"}
        )


def test_area_recon_is_not_a_workflow_step():
    # §4: AREA_RECON is independent of the incident chain.
    with pytest.raises(ValidationError):
        _envelope({"kind": "UPDATE_MISSION", "up_to_step": "AREA_RECON"})


# -- strict typing --------------------------------------------------


def test_coerced_types_are_rejected():
    with pytest.raises(ValidationError):
        _envelope({"kind": "REPORT_INCIDENT", "zone_ref": 123})
    with pytest.raises(ValidationError):
        _envelope({"kind": "QUERY_STATUS", "about": "AGENTS"})  # wrong case


def test_extra_top_level_key_on_envelope_is_rejected():
    with pytest.raises(ValidationError):
        IntentEnvelope.model_validate(
            {"intent": {"kind": "NEW_MISSION"}, "confidence": 0.9}
        )


# -- D-034: API wire shape stays flat, then restores the internal union ---


def test_wire_schema_has_no_openai_rejected_one_of_and_requires_every_key():
    schema = IntentWireEnvelope.model_json_schema()
    assert '"oneOf"' not in json.dumps(schema)
    assert set(schema["required"]) == set(schema["properties"])
    assert set(schema["properties"]) == {
        "kind",
        "zone_ref",
        "target_phrase",
        "up_to_step",
        "incident_response_up_to",
        "response_up_to",
        "about",
        "note",
    }


@pytest.mark.parametrize(
    ("wire", "expected_type", "expected"),
    [
        (
            wire_intent(
                "NEW_MISSION", incident_response_up_to="GROUND_SUPPRESSION"
            ),
            NewMissionIntent,
            {"incident_response_up_to": "GROUND_SUPPRESSION"},
        ),
        (
            wire_intent(
                "REPORT_INCIDENT",
                zone_ref="A 구역",
                response_up_to="SUPPRESSANT_DROP",
            ),
            ReportIncidentIntent,
            {"zone_ref": "A 구역", "response_up_to": "SUPPRESSANT_DROP"},
        ),
        (
            wire_intent(
                "UPDATE_MISSION",
                target_phrase="거기",
                up_to_step="GROUND_SUPPRESSION",
            ),
            UpdateMissionIntent,
            {"target_phrase": "거기", "up_to_step": "GROUND_SUPPRESSION"},
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
def test_wire_converts_deterministically_to_the_internal_discriminated_union(
    wire, expected_type, expected
):
    internal = wire.to_internal().intent
    assert isinstance(internal, expected_type)
    for key, value in expected.items():
        assert getattr(internal, key) == value


@pytest.mark.parametrize(
    ("kind", "irrelevant"),
    [
        ("NEW_MISSION", {"zone_ref": "ZONE_A"}),
        ("NEW_MISSION", {"response_up_to": "GROUND_SUPPRESSION"}),
        ("REPORT_INCIDENT", {"target_phrase": "거기"}),
        ("REPORT_INCIDENT", {"incident_response_up_to": "GROUND_SUPPRESSION"}),
        ("UPDATE_MISSION", {"about": "mission"}),
        ("QUERY_STATUS", {"up_to_step": "GROUND_SUPPRESSION"}),
        ("UNSUPPORTED", {"zone_ref": "ZONE_A"}),
    ],
)
def test_wire_rejects_non_null_slots_owned_by_another_kind(kind, irrelevant):
    with pytest.raises(ValidationError, match="cannot populate slots"):
        wire_intent(kind, **irrelevant)


def test_wire_requires_explicit_nulls_and_strict_types():
    payload = wire_intent("QUERY_STATUS").model_dump()
    payload.pop("note")
    with pytest.raises(ValidationError):
        IntentWireEnvelope.model_validate(payload)

    payload = wire_intent("REPORT_INCIDENT").model_dump()
    payload["zone_ref"] = 123
    with pytest.raises(ValidationError):
        IntentWireEnvelope.model_validate(payload)


def test_intent_prompt_explains_the_flat_null_slot_protocol():
    prompt = intent_system("PHASE: PLANNING")
    assert "kind, zone_ref, target_phrase" in prompt
    assert "incident_response_up_to, response_up_to" in prompt
    assert "use null" in prompt


def test_resource_constraints_are_fail_closed_in_the_prompt():
    prompt = intent_system("PHASE: PLANNING")
    assert "particular robot" in prompt
    assert "UNSUPPORTED as a whole" in prompt


def test_classifier_requests_wire_schema_then_returns_internal_intent():
    backend = MockBackend([wire_intent("QUERY_STATUS", about="agents")])
    session = MissionSession("WIRE", load_scene(SCENE))

    result = classify(session, "로봇 상태", backend)

    assert isinstance(result, QueryStatusIntent)
    assert result.about == "agents"
    assert backend.calls[0][2] == "IntentWireEnvelope"
