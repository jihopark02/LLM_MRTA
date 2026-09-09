"""D-074: pre-registered stress sets for the single-call adoption decision.

Mock-only — checks the sets load, self-check against the Validator, and drive
the ablation harness. Real numbers and the actual gate outcome come from a
live run the operator triggers.
"""

from pathlib import Path

import pytest

from evaluation.graph_gen_ablation import (
    _mock_backend_for,
    gates,
    load_cases,
    paired_latency,
    run,
)
from evaluation.stress_annotations import CASE_IDS, load_stress_set
from scenarios.scene import load_scene

SCENARIOS = Path(__file__).parents[1] / "scenarios"


@pytest.mark.parametrize(
    ("set_name", "scene_file", "count"),
    [("linguistic", "industrial_park.yaml", 19), ("scale", "stress_grid.yaml", 15)],
)
def test_stress_set_loads_and_self_checks(set_name, scene_file, count):
    scene = load_scene(SCENARIOS / scene_file)
    cases = load_stress_set(set_name, scene)  # raises if any allowed_graph fails the Validator
    assert [c.id for c in cases] == list(CASE_IDS[set_name])
    assert len(cases) == count
    # every reject case names an expected failure_category; every safety case
    # carries the prerequisite-restored reference graph
    for c in cases:
        if c.expect == "reject":
            assert c.reject_category and not c.allowed_graphs and c.mock_graph
        if c.expect == "safety-invariant":
            assert c.allowed_graphs and c.mock_graph


@pytest.mark.parametrize("set_name", ["linguistic", "scale"])
def test_stress_set_drives_the_ablation_harness(set_name):
    scene, cases = load_cases(set_name)
    runs = run(scene, _mock_backend_for(cases), cases)

    two = next(r for r in runs if r.mode == "two-stage").summary()
    one = next(r for r in runs if r.mode == "single-call").summary()

    # single-call halves the graph-generation calls; a mocked perfect run keeps
    # graph quality identical between the two modes
    assert one["llm_calls_total"] < two["llm_calls_total"]
    assert one["exact_match"] == two["exact_match"]
    assert one["reject_correct"] == two["reject_correct"] == one["reject_cases"]
    assert one["safety_invalid_accept"] == 0

    g = gates(runs, gate_enabled=True)
    # the graph-quality / reject / safety gates pass on a mocked perfect run;
    # the latency gate is meaningless under mock (no real wall time) so it is
    # not asserted here
    assert g["checks"]["exact_match"]
    assert g["checks"]["first_pass_valid"]
    assert g["checks"]["explicit_reject"]
    assert g["checks"]["safety_invalid_acceptance"]


def test_p6_set_reports_no_gate():
    scene, cases = load_cases("p6")
    runs = run(scene, _mock_backend_for(cases), cases)
    assert gates(runs, gate_enabled=False)["enabled"] is False
    assert paired_latency(runs)["n"] == len(cases)


def test_safety_case_bare_suppression_is_flagged():
    from core.enums import TaskType
    from evaluation.graph_gen_ablation import _bare_suppression
    from validator.candidate import CandidateEdge, CandidateTask, MissionCandidate

    insp, supp = TaskType.GROUND_INSPECTION, TaskType.GROUND_SUPPRESSION
    bare = MissionCandidate([CandidateTask(supp, "FIRE_SITE_1")], [])
    ok = MissionCandidate(
        [CandidateTask(insp, "FIRE_SITE_1"), CandidateTask(supp, "FIRE_SITE_1")],
        [CandidateEdge((insp, "FIRE_SITE_1"), (supp, "FIRE_SITE_1"))],
    )
    assert _bare_suppression(bare) is True
    assert _bare_suppression(ok) is False
