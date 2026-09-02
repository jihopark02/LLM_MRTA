"""P6.5 gate (RESEARCH_CONTRACT.md §15, D-025, D-026): end-to-end integration.

One NL command -> generate_mission (RQ1); the validated graph then forks to
allocate (plan-time) and SimExecutor (event-driven execution) — RQ2. Driven by
a MockBackend so the gate needs no network. The gate checks the graph is the
RIGHT one for the command (annotation exact-match), not merely a valid one.
"""

from pathlib import Path

import pytest

from evaluation.annotations import load_all
from evaluation.integration import _mock_backend, run_commands, run_full, text_report, to_dict
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


def test_representative_commands_demo_pass(scene, annotations):
    anns = _by_id(annotations, "A1", "B1", "C1")
    runs = run_commands(anns, scene, _mock_backend(anns))

    assert [r.id for r in runs] == ["A1", "B1", "C1"]
    for r in runs:
        assert r.harness_error is None
        assert r.approved, r.gen.failure_category
        # the graph is the RIGHT one for the command, not just a valid one
        assert r.exact_match, (r.id, r.score)
        # plan-time CBBA: no violations, everything assigned
        assert r.allocation.allocation_success and not r.allocation.unassigned_tasks
        assert not r.allocation.capability_violations
        assert not r.allocation.precedence_violations
        # event-driven execution: completed cleanly
        assert r.execution.termination.value == "COMPLETED"
        assert not r.execution.unfinished_tasks
        assert not r.execution.capability_violations
        assert not r.execution.precedence_violations
        assert r.operationally_clean and r.demo_pass
    assert "3/3 demo_pass" in text_report(runs)


def test_wrong_but_valid_graph_is_operationally_clean_but_not_demo_pass(scene, annotations):
    # Feed C1's command the C2 canonical graph (both 9 tasks / 3 edges, valid,
    # runnable) — operationally clean, but the wrong decomposition.
    from llm.backend import MockBackend
    from llm.schemas import LLMEdge, LLMTask, Step1Output, Step2Output

    (c1,) = _by_id(annotations, "C1")
    (c2,) = _by_id(annotations, "C2")
    g = c2.allowed_graphs[0]
    tasks = [
        LLMTask(task_type=tt.value, target=tg)
        for tt, tg in sorted(g.tasks, key=lambda k: (k[0].value, k[1]))
    ]
    edges = [
        LLMEdge(predecessor=f"{p[0].value}:{p[1]}", successor=f"{s[0].value}:{s[1]}")
        for p, s in g.edges
    ]
    backend = MockBackend([Step1Output(tasks=tasks), Step2Output(edges=edges)])

    r = run_full(c1, scene, backend)
    assert r.approved and r.operationally_clean
    assert not r.exact_match and not r.demo_pass
    assert r.score.tasks.fp > 0 or r.score.tasks.fn > 0


def test_a1_llm_graph_is_identical_to_the_p1_fixture(scene, annotations):
    # A1's canonical graph IS the hand-authored reference fixture. Check real
    # graph identity (hash + key sets), then that the full pipeline reproduces
    # the P3/P4 golden makespan — the LLM path and the fixture path converge.
    from allocation.allocate import allocate
    from core.mission_state import MissionState
    from execution.executor import SimExecutor
    from validator.candidate import MissionCandidate
    from validator.validate import validate_candidate

    lf = load_reference_fixture()
    fixture_raw = {
        "tasks": [
            {"task_type": t.task_type.value, "target": t.target} for t in lf.graph.tasks
        ],
        "edges": [
            [f"{lf.graph[p].task_type.value}:{lf.graph[p].target}",
             f"{lf.graph[s].task_type.value}:{lf.graph[s].target}"]
            for p, s in lf.graph.edges
        ],
    }
    fixture_cand, errs = MissionCandidate.from_raw(fixture_raw)
    assert errs == []
    fixture_hash = validate_candidate(fixture_cand, lf.scene).graph_hash

    (a1,) = _by_id(annotations, "A1")
    r = run_full(a1, scene, _mock_backend([a1]))

    assert r.final_snapshot.graph_hash == fixture_hash  # real graph identity
    got_tasks = {(t["task_type"], t["target"]) for t in r.final_snapshot.tasks}
    got_edges = {tuple(e) for e in r.final_snapshot.edges}
    want_tasks = {(t["task_type"], t["target"]) for t in fixture_raw["tasks"]}
    want_edges = {tuple(e) for e in fixture_raw["edges"]}
    assert got_tasks == want_tasks and got_edges == want_edges

    fleet = {a.agent_id: a for a in lf.scene.fleet}
    golden_alloc = allocate(MissionState(lf.graph, fleet), lf.scene).estimated_makespan
    golden_exec = SimExecutor(MissionState(lf.graph, fleet), lf.scene).run().makespan
    assert r.allocation.estimated_makespan == pytest.approx(golden_alloc)
    assert r.execution.makespan == pytest.approx(golden_exec)


def test_audit_json_carries_graph_hash_and_both_assignment_maps(scene, annotations):
    anns = _by_id(annotations, "A1", "B1")
    runs = run_commands(anns, scene, _mock_backend(anns))
    d = to_dict(runs, scene, requested_model=None, started_at="t0", finished_at="t1")

    assert d["meta"]["validator_version"] == "1.3"
    assert d["meta"]["scene_hash"]
    a1 = d["cases"][0]
    assert len(a1["generation"]["tasks"]) == 12 and len(a1["generation"]["edges"]) == 6
    assert len(a1["generation"]["graph_hash"]) == 64
    assert a1["generation"]["score"]["task"] == {"tp": 12, "fp": 0, "fn": 0}
    # MRTA outputs: task -> agent for both the plan and the execution
    assert set(a1["plan_analysis"]["assignments"]) == {
        f"{t['task_type']}__{t['target']}" for t in a1["generation"]["tasks"]
    }
    assert set(a1["execution"]["assignments"]) == set(a1["plan_analysis"]["assignments"])
    assert a1["execution"]["termination"] == "COMPLETED"


def test_rejected_mission_stops_before_allocation(scene, annotations):
    from llm.backend import MockBackend
    from llm.schemas import LLMTask as T
    from llm.schemas import RepairOutput, Step1Output, Step2Output

    (a1,) = _by_id(annotations, "A1")
    drop = [T(task_type="SUPPRESSANT_DROP", target="FIRE_SITE_1")]
    broken = MockBackend([
        Step1Output(tasks=drop),
        Step2Output(edges=[]),
        RepairOutput(tasks=drop, edges=[]),  # repair returns the same broken graph
    ])
    r = run_full(a1, scene, broken)
    assert not r.approved
    assert r.allocation is None and r.execution is None
    assert not r.operationally_clean and not r.demo_pass


def test_harness_error_is_recorded_not_raised(scene, annotations):
    class Boom:
        def complete(self, *a, **k):
            raise RuntimeError("network down")

    (a1,) = _by_id(annotations, "A1")
    r = run_full(a1, scene, Boom())
    assert r.harness_error is not None and "network down" in r.harness_error
    assert not r.approved and not r.demo_pass
    assert r.allocation is None and r.execution is None
