"""P5 gate (RESEARCH_CONTRACT.md §12, §15): LLM pipeline with a mock backend.

No network, no API key — every path is driven by scripted MockBackend responses.
"""

from pathlib import Path

import pytest

from llm.backend import MockBackend
from llm.pipeline import generate_mission
from llm.schemas import LLMEdge, LLMTask, RepairOutput, Step1Output, Step2Output
from scenarios.scene import load_scene

SCENE = Path(__file__).parents[1] / "scenarios" / "industrial_park.yaml"


@pytest.fixture
def scene():
    return load_scene(SCENE)


def t(tt, target, prio):
    return LLMTask(task_type=tt, target=target, priority=prio)


def e(pred, succ):
    return LLMEdge(predecessor=pred, successor=succ)


# -- approved on the first attempt ------------------------------------


def test_valid_mission_is_approved_and_compiled(scene):
    step1 = Step1Output(tasks=[t("AREA_RECON", "ZONE_A", 3), t("THERMAL_RECON", "FIRE_SITE_1", 9)])
    step2 = Step2Output(edges=[])
    backend = MockBackend([step1, step2])

    r = generate_mission("Scout ZONE_A and check FIRE_SITE_1.", scene, backend)

    assert r.approved and r.attempts == 1 and not r.repaired
    assert r.raw_schema_valid and r.raw_whole_graph_valid
    assert r.repaired_schema_valid is None and r.repaired_whole_graph_valid is None
    assert r.failure_category is None
    assert r.raw_candidate is r.candidate and r.raw_validation is r.validation
    assert r.graph is not None and len(r.graph) == 2
    assert [c[2] for c in backend.calls] == ["Step1Output", "Step2Output"]


def test_full_incident_workflow_is_approved(scene):
    chain = [
        t("THERMAL_RECON", "FIRE_SITE_1", 9),
        t("SUPPRESSANT_DROP", "FIRE_SITE_1", 9),
        t("GROUND_INSPECTION", "FIRE_SITE_1", 9),
        t("GROUND_SUPPRESSION", "FIRE_SITE_1", 9),
    ]
    edges = [
        e("THERMAL_RECON:FIRE_SITE_1", "SUPPRESSANT_DROP:FIRE_SITE_1"),
        e("SUPPRESSANT_DROP:FIRE_SITE_1", "GROUND_INSPECTION:FIRE_SITE_1"),
        e("GROUND_INSPECTION:FIRE_SITE_1", "GROUND_SUPPRESSION:FIRE_SITE_1"),
    ]
    backend = MockBackend([Step1Output(tasks=chain), Step2Output(edges=edges)])
    r = generate_mission("Full response to FIRE_SITE_1.", scene, backend)
    assert r.approved and len(r.graph) == 4 and len(r.graph.edges) == 3


# -- Step 1 schema gate blocks Step 2 --------------------------------


def test_unknown_task_type_never_reaches_step2(scene):
    # task_type is a bare str in the schema (pydantic can't know the enum) —
    # MissionCandidate.from_raw is what rejects an unknown type.
    step1 = Step1Output(tasks=[t("WATER_LOAD", "ZONE_A", 3)])
    backend = MockBackend([step1])  # only ONE scripted response: Step 2 must not be asked

    r = generate_mission("Load water.", scene, backend)

    assert not r.approved and r.attempts == 1 and not r.repaired
    assert r.failure_category == "SCHEMA" and not r.raw_schema_valid
    assert r.graph is None
    assert [c[2] for c in backend.calls] == ["Step1Output"]  # Step 2 never called


def test_duplicate_task_in_step1_never_reaches_step2(scene):
    step1 = Step1Output(tasks=[t("AREA_RECON", "ZONE_A", 3), t("AREA_RECON", "ZONE_A", 5)])
    backend = MockBackend([step1])
    r = generate_mission("...", scene, backend)
    assert not r.approved and r.failure_category == "SCHEMA"
    assert [c[2] for c in backend.calls] == ["Step1Output"]


# -- pydantic strict/forbid: extra fields and coerced types are schema errors --


def test_extra_field_on_task_is_rejected_without_calling_step2(scene):
    bad = {
        "tasks": [
            {"task_type": "AREA_RECON", "target": "ZONE_A", "priority": 3, "position": [1, 2]}
        ]
    }
    backend = MockBackend([bad])
    r = generate_mission("...", scene, backend)
    assert not r.approved and r.failure_category == "SCHEMA"
    assert [c[2] for c in backend.calls] == ["Step1Output"]  # Step 2 never called


def test_string_priority_is_rejected(scene):
    bad = {"tasks": [{"task_type": "AREA_RECON", "target": "ZONE_A", "priority": "3"}]}
    r = generate_mission("...", scene, MockBackend([bad]))
    assert not r.approved and r.failure_category == "SCHEMA"


def test_bool_priority_is_rejected(scene):
    bad = {"tasks": [{"task_type": "AREA_RECON", "target": "ZONE_A", "priority": True}]}
    r = generate_mission("...", scene, MockBackend([bad]))
    assert not r.approved and r.failure_category == "SCHEMA"


def test_extra_field_on_edge_is_rejected(scene):
    step1 = Step1Output(tasks=[t("AREA_RECON", "ZONE_A", 3), t("AREA_RECON", "ZONE_B", 3)])
    bad_step2 = {
        "edges": [
            {"predecessor": "AREA_RECON:ZONE_A", "successor": "AREA_RECON:ZONE_B", "reason": "x"}
        ]
    }
    r = generate_mission("...", scene, MockBackend([step1, bad_step2]))
    assert not r.approved and r.failure_category == "SCHEMA"


def test_extra_top_level_field_is_rejected(scene):
    bad = {"tasks": [{"task_type": "AREA_RECON", "target": "ZONE_A", "priority": 3}], "notes": "x"}
    r = generate_mission("...", scene, MockBackend([bad]))
    assert not r.approved and r.failure_category == "SCHEMA"


# -- one repair pass fixes it --------------------------------------


def test_workflow_error_is_repaired_then_approved(scene):
    # Step 1 forgets THERMAL_RECON -> SUPPRESSANT_DROP fails #10 (E_WORKFLOW).
    step1 = Step1Output(tasks=[t("SUPPRESSANT_DROP", "FIRE_SITE_1", 9)])
    step2 = Step2Output(edges=[])
    repair = RepairOutput(
        tasks=[t("THERMAL_RECON", "FIRE_SITE_1", 9), t("SUPPRESSANT_DROP", "FIRE_SITE_1", 9)],
        edges=[e("THERMAL_RECON:FIRE_SITE_1", "SUPPRESSANT_DROP:FIRE_SITE_1")],
    )
    backend = MockBackend([step1, step2, repair])

    r = generate_mission("Drop on FIRE_SITE_1.", scene, backend)

    assert r.approved and r.attempts == 2 and r.repaired
    assert r.raw_schema_valid and not r.raw_whole_graph_valid
    assert r.repaired_schema_valid and r.repaired_whole_graph_valid
    assert r.failure_category is None
    assert [c[2] for c in backend.calls] == ["Step1Output", "Step2Output", "RepairOutput"]
    assert len(r.graph) == 2

    # raw output is preserved distinctly from the repaired/final one
    assert r.raw_candidate is not None and len(r.raw_candidate.tasks) == 1
    assert not r.raw_validation.accepted
    assert r.candidate is not r.raw_candidate
    assert len(r.candidate.tasks) == 2

    # the repair prompt actually carried the structured errors and the raw graph
    repair_call_user = backend.calls[2][1]
    assert "E_WORKFLOW" in repair_call_user
    assert "SUPPRESSANT_DROP" in repair_call_user


# -- explicit rejection, no silent fallback -----------------------


def test_repair_that_still_fails_is_explicitly_rejected(scene):
    step1 = Step1Output(tasks=[t("SUPPRESSANT_DROP", "FIRE_SITE_1", 9)])
    step2 = Step2Output(edges=[])
    repair = RepairOutput(tasks=[t("SUPPRESSANT_DROP", "FIRE_SITE_1", 9)], edges=[])  # still broken
    backend = MockBackend([step1, step2, repair])

    r = generate_mission("Drop on FIRE_SITE_1.", scene, backend)

    assert not r.approved and r.attempts == 2 and r.repaired
    assert r.failure_category == "WORKFLOW"
    assert r.graph is None  # never falls back to the reference
    assert r.errors
    # raw candidate/validation from before the failed repair are still there
    assert r.raw_candidate is not None and not r.raw_validation.accepted


def test_cross_incident_edge_is_rejected_when_repair_fails(scene):
    step1 = Step1Output(
        tasks=[t("THERMAL_RECON", "FIRE_SITE_1", 9), t("SUPPRESSANT_DROP", "FIRE_SITE_2", 7)]
    )
    step2 = Step2Output(
        edges=[e("THERMAL_RECON:FIRE_SITE_1", "SUPPRESSANT_DROP:FIRE_SITE_2")]
    )
    repair = RepairOutput(tasks=step1.tasks, edges=step2.edges)  # unchanged -> still fails
    r = generate_mission("...", scene, MockBackend([step1, step2, repair]))
    assert not r.approved and r.failure_category == "WORKFLOW"


def test_backend_running_dry_is_an_error(scene):
    backend = MockBackend([Step1Output(tasks=[t("AREA_RECON", "ZONE_A", 3)])])  # missing Step 2
    with pytest.raises(AssertionError, match="ran out of scripted"):
        generate_mission("...", scene, backend)
