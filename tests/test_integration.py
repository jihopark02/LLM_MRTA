"""P6.5 gate (RESEARCH_CONTRACT.md §15, D-025): thin end-to-end runner.

One NL command through generate_mission -> allocate -> SimExecutor, driven by a
MockBackend so the gate needs no network. Proves RQ1 (P6) and RQ2 (P3/P4)
actually connect.
"""

from pathlib import Path

import pytest

from evaluation.annotations import load_all
from evaluation.integration import _mock_backend, run_commands, run_full, text_report
from scenarios.fixture import load_reference_fixture
from scenarios.scene import load_scene

SCENE = Path(__file__).parents[1] / "scenarios" / "industrial_park.yaml"


@pytest.fixture(scope="module")
def scene():
    return load_scene(SCENE)


@pytest.fixture(scope="module")
def annotations(scene):
    return load_all(scene)


def _by_id(annotations, *ids):
    m = {a.id: a for a in annotations}
    return [m[i] for i in ids]


def test_representative_commands_run_clean_through_the_pipeline(scene, annotations):
    anns = _by_id(annotations, "A1", "B1", "C1")
    runs = run_commands(anns, scene, _mock_backend(anns))

    assert [r.id for r in runs] == ["A1", "B1", "C1"]
    for r in runs:
        assert r.approved, r.gen.failure_category
        assert r.allocation.allocation_success and not r.allocation.unassigned_tasks
        assert not r.allocation.capability_violations
        assert not r.allocation.precedence_violations
        assert not r.execution.deadlocked and not r.execution.unfinished_tasks
        assert not r.execution.capability_violations
        assert not r.execution.precedence_violations
        assert r.clean
    assert "3/3" in text_report(runs)


def test_a1_llm_graph_matches_the_p1_fixture_allocation(scene, annotations):
    # A1's canonical graph is exactly the hand-authored reference fixture
    # (12 tasks / 6 edges), so the full pipeline must reproduce the P3/P4
    # golden makespan — the LLM path and the fixture path converge.
    from allocation.allocate import allocate
    from core.mission_state import MissionState
    from execution.executor import SimExecutor

    lf = load_reference_fixture()
    fleet = {a.agent_id: a for a in lf.scene.fleet}
    golden_alloc = allocate(MissionState(lf.graph, fleet), lf.scene).estimated_makespan
    golden_exec = SimExecutor(MissionState(lf.graph, fleet), lf.scene).run().makespan

    (a1,) = _by_id(annotations, "A1")
    r = run_full(a1.command, scene, _mock_backend([a1]), run_id="A1")
    assert len(r.gen.graph) == 12 and len(r.gen.graph.edges) == 6
    assert r.allocation.estimated_makespan == pytest.approx(golden_alloc)
    assert r.execution.makespan == pytest.approx(golden_exec)


def test_rejected_mission_stops_before_allocation(scene, annotations):
    from llm.backend import MockBackend
    from llm.schemas import LLMTask as T
    from llm.schemas import RepairOutput, Step1Output, Step2Output

    (a1,) = _by_id(annotations, "A1")
    drop = [T(task_type="SUPPRESSANT_DROP", target="FIRE_SITE_1")]
    # SUPPRESSANT_DROP with no THERMAL_RECON predecessor -> E_WORKFLOW; repair
    # returns the same broken graph -> explicit rejection, no fallback.
    broken = MockBackend([
        Step1Output(tasks=drop),
        Step2Output(edges=[]),
        RepairOutput(tasks=drop, edges=[]),
    ])
    r = run_full(a1.command, scene, broken, run_id="A1")
    assert not r.approved
    assert r.allocation is None and r.execution is None
    assert not r.clean
