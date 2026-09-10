"""D-071: per-turn latency instrumentation (§18.9 TurnAudit.timing)."""

import time
from pathlib import Path

import pytest

from interaction.orchestrator import handle_turn
from interaction.schemas import wire_intent
from interaction.session import MissionSession, fresh_session_state
from llm.backend import MockBackend, TimedBackend
from llm.schemas import LLMTask, Step1Output
from scenarios.compiler import compile_reference_graph
from scenarios.scene import load_scene
from tests.ir_fixtures import response_ir

SCENE = Path(__file__).parents[1] / "scenarios" / "industrial_park.yaml"


@pytest.fixture
def scene():
    return load_scene(SCENE)


def _new_mission_backend():
    return MockBackend(
        [wire_intent("NEW_MISSION",
                     mission=response_ir("GROUND_SUPPRESSION", explicit=("FIRE_SITE_1",)))]
    )


def test_timed_backend_delegates_mode_and_records_each_call():
    inner = MockBackend([Step1Output(tasks=[LLMTask(task_type="AREA_RECON", target="ZONE_A")])])
    timed = TimedBackend(inner)
    assert timed.mode == "mock"

    timed.complete("s", "u", Step1Output)
    assert [name for name, _ in timed.calls] == ["Step1Output"]
    assert all(seconds >= 0.0 for _, seconds in timed.calls)


def test_timed_backend_measures_real_wall_time():
    class Slow:
        mode = "live"

        def complete(self, *a, **k):
            time.sleep(0.02)
            return Step1Output(tasks=[LLMTask(task_type="AREA_RECON", target="ZONE_A")])

    timed = TimedBackend(Slow())
    timed.complete("s", "u", Step1Output)
    assert timed.calls[0][1] >= 0.015


def test_new_mission_turn_records_one_llm_call(scene):
    # D-076: kind + Semantic Mission IR are a single semantic-interpretation call.
    session = MissionSession("LAT", scene)
    result = handle_turn(session, "FIRE_SITE_1 대응 시작", _new_mission_backend())

    assert result.outcome.value == "COMMITTED"
    timing = result.audit.timing
    assert timing is not None
    assert [name for name, _ in timing.llm_calls] == ["IntentWireEnvelope"]
    assert timing.total_s >= 0.0
    assert timing.llm_total_s == pytest.approx(
        sum(seconds for _, seconds in timing.llm_calls)
    )
    assert timing.deterministic_s == pytest.approx(
        max(0.0, timing.total_s - timing.llm_total_s)
    )


def test_report_incident_turn_records_only_the_intent_call(scene):
    from allocation.allocate import allocate
    from core.enums import TaskType

    graph = compile_reference_graph(scene, [(TaskType.AREA_RECON, "ZONE_A")], [])
    state = fresh_session_state(graph, scene)
    session = MissionSession("LAT", scene, state=state, plan=allocate(state, scene))

    result = handle_turn(
        session,
        "Processing Area에서 불이 났어",
        MockBackend([wire_intent("REPORT_INCIDENT", zone_ref="Processing Area")]),
    )

    assert result.outcome.value in {"COMMITTED", "NO_CHANGE"}
    assert [name for name, _ in result.audit.timing.llm_calls] == ["IntentWireEnvelope"]


def test_latency_aggregator_groups_by_intent_kind(scene, tmp_path):
    from evaluation.latency import collect
    from interaction.audit_io import write_session_audit

    for i in range(3):
        session = MissionSession(f"agg{i}", scene)
        handle_turn(session, "FIRE_SITE_1 대응 시작", _new_mission_backend())
        handle_turn(session, "지금 상황", MockBackend([wire_intent("QUERY_STATUS")]))
        write_session_audit(session, tmp_path)

    summary = collect(tmp_path, mode=None)

    assert summary["NEW_MISSION"]["n"] == 3
    assert summary["QUERY_STATUS"]["n"] == 3
    assert set(summary["NEW_MISSION"]["llm_calls"]) == {"IntentWireEnvelope"}
    assert set(summary["QUERY_STATUS"]["llm_calls"]) == {"IntentWireEnvelope"}
    assert summary["NEW_MISSION"]["total_s"]["mean"] >= 0.0
