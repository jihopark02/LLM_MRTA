"""P8.2 gate: the session audit trail on disk (§15 P8.2, §18.9, D-029).

§18.9 fixes the record shape AND the path, so the phase owes a real file. The
payload is an event stream so P8.3's ExecutionAudit slots in beside the turns.
"""

import json
from pathlib import Path

import pytest

from interaction.audit import ExecutionAudit
from interaction.audit_io import (
    AUDIT_DIR,
    audit_path,
    session_audit_json,
    session_audit_payload,
    write_session_audit,
)
from interaction.orchestrator import handle_turn
from interaction.schemas import IntentWireEnvelope, wire_intent
from interaction.session import MissionSession
from llm.backend import MockBackend
from scenarios.scene import load_scene
from tests.ir_fixtures import response_ir

SCENE = Path(__file__).parents[1] / "scenarios" / "industrial_park.yaml"


@pytest.fixture
def scene():
    return load_scene(SCENE)


def intent(kind: str, **slots) -> IntentWireEnvelope:
    return wire_intent(kind, **slots)


class _Boom:
    mode = "live"

    def complete(self, *a, **k):
        raise RuntimeError("네트워크 오류")


@pytest.fixture
def seven_turn_session(scene):
    """The §18 worked dialogue, plus a failing turn so the error path is in it."""
    s = MissionSession(session_id="DEMO", scene=scene)
    turns = [
        ("FIRE_SITE_1 대응 시작", MockBackend([
            intent("NEW_MISSION",
                   mission=response_ir("GROUND_SUPPRESSION", explicit=("FIRE_SITE_1",))),
        ])),
        ("그 화재 진압까지", MockBackend([
            intent("UPDATE_MISSION",
                   mission=response_ir("GROUND_SUPPRESSION", deixis="그 화재"))
        ])),
        ("A 구역에 화재", MockBackend([intent("REPORT_INCIDENT", zone_ref="A 구역")])),
        ("거기부터 꺼줘", MockBackend([
            intent("UPDATE_MISSION",
                   mission=response_ir("GROUND_SUPPRESSION", deixis="거기"))
        ])),
        ("거기 로봇 누구야", MockBackend([
            intent("QUERY_STATUS", about="agents", target_phrase="거기")
        ])),
        ("G1 취소해", MockBackend([intent("UNSUPPORTED", note="cancel")])),
        ("뭐든", _Boom()),
    ]
    for utterance, backend in turns:
        handle_turn(s, utterance, backend)
    return s


# -- payload shape ----------------------------------------------------


def test_every_turn_appears_as_an_event(seven_turn_session):
    payload = session_audit_payload(seven_turn_session)
    assert payload["session_id"] == "DEMO"
    assert payload["turn_count"] == 7
    assert len(payload["events"]) == 7
    assert [e["turn_id"] for e in payload["events"]] == [f"t{i}" for i in range(1, 8)]
    assert [e["event_seq"] for e in payload["events"]] == list(range(7))
    assert {e["event_type"] for e in payload["events"]} == {"TURN"}


def test_payload_carries_the_reproducibility_fields(seven_turn_session):
    payload = session_audit_payload(seven_turn_session)
    assert len(payload["scene_hash"]) == 64
    assert payload["validator_version"] == "1.4"
    assert payload["phase"] == "PLANNING"


def test_outcomes_are_recorded_in_order(seven_turn_session):
    outcomes = [e["outcome"] for e in session_audit_payload(seven_turn_session)["events"]]
    assert outcomes == [
        "COMMITTED",       # NEW_MISSION
        "CLARIFICATION",   # "그 화재" with two incidents
        "COMMITTED",       # REPORT
        "COMMITTED",       # "거기" -> the new incident
        "ANSWERED",        # deictic QUERY
        "UNSUPPORTED",
        "TURN_ERROR",
    ]


def test_turn_error_cause_survives_in_the_file(seven_turn_session):
    last = session_audit_payload(seven_turn_session)["events"][-1]
    assert last["outcome"] == "TURN_ERROR"
    assert last["error_type"] == "RuntimeError"
    assert "네트워크 오류" in last["error_detail"]


def test_grounding_and_patch_detail_survive(seven_turn_session):
    events = session_audit_payload(seven_turn_session)["events"]

    clarified = events[1]
    assert clarified["grounding"]["status"] == "CLARIFICATION_REQUIRED"
    assert clarified["grounding"]["reason"] == "AMBIGUOUS_ENTITY"
    # S8: a mission-edit clarification does not offer a candidate list
    assert clarified["grounding"]["candidates"] == []
    assert clarified["semantic_ir"]["clarification_reason"] == "AMBIGUOUS_ENTITY"

    extended = events[3]
    # D-076: a mission edit's grounding lives per-clause in semantic_ir
    assert extended["semantic_ir"]["responses"][0]["targets"] == ["FIRE_SITE_3"]
    assert extended["semantic_ir"]["responses"][0]["operator"].startswith("DEIXIS(거기)")
    assert extended["patch"]["accepted"] and extended["patch"]["added_tasks"]
    assert len(extended["patch_hash"]) == 64 and len(extended["pre_state_hash"]) == 64
    assert extended["pre_graph_hash"] != extended["post_graph_hash"]
    assert extended["plan_assignment_changes"]["added"]


def test_mode_and_models_are_recorded_per_turn(seven_turn_session):
    events = session_audit_payload(seven_turn_session)["events"]
    assert {e["mode"] for e in events} == {"mock", "live"}  # the _Boom turn is live
    assert events[0]["mode"] == "mock"
    assert events[-1]["mode"] == "live"


def test_scene_and_state_change_flags(seven_turn_session):
    events = session_audit_payload(seven_turn_session)["events"]
    report = events[2]
    assert report["scene_changed"] and not report["state_changed"]
    assert events[3]["state_changed"] and not events[3]["scene_changed"]
    assert not events[4]["state_changed"] and not events[4]["scene_changed"]  # QUERY


# -- serialization ----------------------------------------------------


def test_korean_is_readable_not_escaped(seven_turn_session):
    text = session_audit_json(seven_turn_session)
    assert "\\u" not in text
    assert "A 구역에 화재" in text
    assert "네트워크 오류" in text


def test_json_is_deterministic(seven_turn_session):
    a = session_audit_json(seven_turn_session)
    b = session_audit_json(seven_turn_session)
    assert a == b
    assert json.loads(a) == session_audit_payload(seven_turn_session)


# -- the file ---------------------------------------------------------


def test_write_creates_the_file_at_the_contract_path(seven_turn_session, tmp_path):
    path = write_session_audit(seven_turn_session, tmp_path)
    assert path == tmp_path / "DEMO.json"
    assert json.loads(path.read_text(encoding="utf-8"))["session_id"] == "DEMO"


def test_write_creates_missing_directories(seven_turn_session, tmp_path):
    path = write_session_audit(seven_turn_session, tmp_path / "nested" / "runs")
    assert path.exists()


def test_default_path_follows_the_contract():
    assert AUDIT_DIR == Path("data/interaction_runs")
    assert audit_path("S1") == Path("data/interaction_runs/S1.json")


def test_rewriting_is_idempotent(seven_turn_session, tmp_path):
    first = write_session_audit(seven_turn_session, tmp_path).read_text(encoding="utf-8")
    second = write_session_audit(seven_turn_session, tmp_path).read_text(encoding="utf-8")
    assert first == second


# -- P8.3 forward compatibility ---------------------------------------


def test_an_execution_record_joins_the_same_event_stream(seven_turn_session):
    # P8.3 appends its ExecutionAudit here without reshaping the payload.
    execution = ExecutionAudit(
        session_id="DEMO",
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
    seven_turn_session.append_event(execution)
    payload = session_audit_payload(seven_turn_session)
    assert len(payload["events"]) == 8
    assert payload["events"][-1]["event_type"] == "EXECUTION"
    assert payload["events"][-1]["execution_termination"] == "COMPLETED"
    assert payload["events"][-1]["event_seq"] == 7
    # every event is self-describing, so a reader can split the stream by type
    assert all("event_type" in e for e in payload["events"])


# -- the id is a path component (§18.9, D-030) ------------------------


@pytest.mark.parametrize("session_id", ["../escape", "../../outside", "/tmp/absolute", "a/b"])
def test_audit_path_refuses_an_id_that_would_leave_the_directory(session_id, tmp_path):
    with pytest.raises(ValueError, match="session_id"):
        audit_path(session_id, tmp_path)


def test_a_bad_id_writes_nothing_and_creates_no_directory(seven_turn_session, tmp_path):
    # MissionSession refuses such an id at construction, so reaching the writer
    # takes a post-construction mutation; the writer must still not act on it.
    target = tmp_path / "runs"
    seven_turn_session.session_id = "../escape"
    with pytest.raises(ValueError, match="session_id"):
        write_session_audit(seven_turn_session, target)
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_writer_rejects_events_from_the_sessions_old_id(seven_turn_session):
    seven_turn_session.session_id = "RENAMED"
    with pytest.raises(ValueError, match="does not match"):
        session_audit_payload(seven_turn_session)


def test_a_good_id_stays_inside_the_directory(tmp_path):
    resolved = audit_path("demo-01", tmp_path).resolve()
    assert resolved.parent == tmp_path.resolve()
