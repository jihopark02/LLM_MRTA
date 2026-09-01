"""Raw candidate parsing + consistency (RESEARCH_CONTRACT.md §12; invariants #1-3, #5-7)."""

import pytest

from core.enums import TaskType
from validator.candidate import CandidateEdge, CandidateTask, MissionCandidate
from validator.errors import ErrorCode

GOOD_RAW = {
    "tasks": [
        {"task_type": "THERMAL_RECON", "target": "FIRE_SITE_1", "priority": 9},
        {"task_type": "SUPPRESSANT_DROP", "target": "FIRE_SITE_1", "priority": 9},
    ],
    "edges": [["THERMAL_RECON:FIRE_SITE_1", "SUPPRESSANT_DROP:FIRE_SITE_1"]],
}


def codes(errs):
    return sorted(e.code for e in errs)


def test_parse_good_candidate():
    cand, errors = MissionCandidate.from_raw(GOOD_RAW)
    assert errors == []
    assert cand.tasks[0] == CandidateTask(TaskType.THERMAL_RECON, "FIRE_SITE_1", 9)
    assert cand.edges[0] == CandidateEdge(
        (TaskType.THERMAL_RECON, "FIRE_SITE_1"), (TaskType.SUPPRESSANT_DROP, "FIRE_SITE_1")
    )
    assert cand.consistency_errors() == []


def test_container_shape_is_schema_error():
    cand, errors = MissionCandidate.from_raw([1, 2, 3])
    assert cand is None
    assert codes(errors) == [ErrorCode.E_SCHEMA]


def test_bad_task_fields_are_schema_errors():
    _, errors = MissionCandidate.from_raw(
        {"tasks": [{"task_type": "AREA_RECON", "target": "ZONE_A"}], "edges": []}
    )
    assert ErrorCode.E_SCHEMA in codes(errors)


def test_bool_priority_rejected_as_schema():
    _, errors = MissionCandidate.from_raw(
        {"tasks": [{"task_type": "AREA_RECON", "target": "ZONE_A", "priority": True}], "edges": []}
    )
    assert ErrorCode.E_SCHEMA in codes(errors)


@pytest.mark.parametrize("bad", [0, -10, 11, 10**9])
def test_priority_out_of_1_to_10_is_schema_error(bad):
    _, errors = MissionCandidate.from_raw(
        {"tasks": [{"task_type": "AREA_RECON", "target": "ZONE_A", "priority": bad}], "edges": []}
    )
    assert codes(errors) == [ErrorCode.E_SCHEMA]


def test_priority_1_and_10_are_accepted():
    for p in (1, 10):
        _, errors = MissionCandidate.from_raw(
            {"tasks": [{"task_type": "AREA_RECON", "target": "ZONE_A", "priority": p}], "edges": []}
        )
        assert errors == []


def test_unknown_task_type_is_type_not_allowed():
    _, errors = MissionCandidate.from_raw(
        {"tasks": [{"task_type": "WATER_LOAD", "target": "ZONE_A", "priority": 1}], "edges": []}
    )
    assert codes(errors) == [ErrorCode.E_TYPE_NOT_ALLOWED]


def test_malformed_edge_endpoint_is_schema_error():
    _, errors = MissionCandidate.from_raw(
        {"tasks": [], "edges": [["THERMAL_RECON_FIRE_SITE_1", "x:y"]]}
    )
    assert ErrorCode.E_SCHEMA in codes(errors)


def test_duplicate_task_key_is_duplicate_id():
    raw = {
        "tasks": [
            {"task_type": "AREA_RECON", "target": "ZONE_A", "priority": 1},
            {"task_type": "AREA_RECON", "target": "ZONE_A", "priority": 2},
        ],
        "edges": [],
    }
    cand, errors = MissionCandidate.from_raw(raw)
    assert errors == []
    assert codes(cand.consistency_errors()) == [ErrorCode.E_DUPLICATE_ID]


def test_duplicate_edge_and_self_loop_and_unknown_endpoint():
    raw = {
        "tasks": [{"task_type": "THERMAL_RECON", "target": "FIRE_SITE_1", "priority": 9}],
        "edges": [
            ["THERMAL_RECON:FIRE_SITE_1", "THERMAL_RECON:FIRE_SITE_1"],  # self-loop
            ["THERMAL_RECON:FIRE_SITE_1", "SUPPRESSANT_DROP:FIRE_SITE_1"],  # unknown endpoint
            ["THERMAL_RECON:FIRE_SITE_1", "SUPPRESSANT_DROP:FIRE_SITE_1"],  # + duplicate
        ],
    }
    cand, errors = MissionCandidate.from_raw(raw)
    assert errors == []
    got = codes(cand.consistency_errors())
    assert ErrorCode.E_SELF_LOOP in got
    assert ErrorCode.E_DUPLICATE_EDGE in got
    assert ErrorCode.E_UNKNOWN_REF in got
