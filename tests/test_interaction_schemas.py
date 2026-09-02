"""P8.1a: operator intent schemas (RESEARCH_CONTRACT.md §18.2, §18.7, D-027).

The classifier's job is narrow by construction: five kinds, slots only, no
clarification member, no task generation. These tests pin the D-027 removals
(`tasks`, `label`, `urgent`, `priority`) at the schema level.
"""

import pytest
from pydantic import ValidationError

from interaction.schemas import (
    IntentEnvelope,
    NewMissionIntent,
    QueryStatusIntent,
    ReportIncidentIntent,
    UnsupportedIntent,
    UpdateMissionIntent,
)


def _envelope(payload: dict) -> IntentEnvelope:
    return IntentEnvelope.model_validate({"intent": payload})


# -- the five supported kinds parse ---------------------------------


def test_new_mission_has_no_slots():
    e = _envelope({"kind": "NEW_MISSION"})
    assert isinstance(e.intent, NewMissionIntent)


def test_report_incident_zone_ref_optional():
    assert _envelope({"kind": "REPORT_INCIDENT"}).intent.zone_ref is None
    got = _envelope({"kind": "REPORT_INCIDENT", "zone_ref": "A 구역"}).intent
    assert isinstance(got, ReportIncidentIntent) and got.zone_ref == "A 구역"


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
