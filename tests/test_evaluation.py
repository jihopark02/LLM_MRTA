"""P6 gate (RESEARCH_CONTRACT.md §12, §15, D-021): evaluation harness.

The metrics are unit-tested directly; the harness is exercised end to end with
a ``MockBackend`` — no network, no API key — driving perfect, imperfect and
schema-broken cases.
"""

from pathlib import Path

import pytest

from core.enums import TaskType
from evaluation.annotations import RefGraph, load_all, load_annotation
from evaluation.harness import run_all
from evaluation.metrics import PRF, score_graph
from evaluation.report import text_report, to_dict
from llm.backend import MockBackend
from llm.schemas import LLMEdge, LLMTask, Step1Output, Step2Output
from scenarios.scene import load_scene
from validator.candidate import MissionCandidate

SCENE = Path(__file__).parents[1] / "scenarios" / "industrial_park.yaml"


@pytest.fixture
def scene():
    return load_scene(SCENE)


@pytest.fixture
def annotations(scene):
    return load_all(scene)


# -- annotations -----------------------------------------------------


def test_all_nine_annotations_load_and_self_check(annotations):
    assert [a.id for a in annotations] == [
        "A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2", "C3"
    ]
    assert [a.family for a in annotations] == list("AAABBBCCC")
    fam_a = [a for a in annotations if a.family == "A"]
    for a in fam_a:  # family A == the P1 reference fixture shape
        g = a.allowed_graphs[0]
        assert len(g.tasks) == 12 and len(g.edges) == 6


def test_family_b_has_no_edges(annotations):
    for a in (x for x in annotations if x.family == "B"):
        g = a.allowed_graphs[0]
        assert len(g.tasks) == 6 and len(g.edges) == 0


def test_non_prefix_chain_is_rejected(scene, tmp_path):
    bad = tmp_path / "X1.yaml"
    bad.write_text(
        "id: X1\nfamily: C\nprofile: SELECTIVE_RESPONSE\n"
        "command: x\nrationale: x\n"
        "allowed_graphs:\n"
        "  - incident_chains:\n"
        "      FIRE_SITE_1: [THERMAL_RECON, GROUND_INSPECTION]\n"
    )
    with pytest.raises(ValueError, match="contiguous prefix"):
        load_annotation(bad, scene)


def test_reference_that_fails_validator_is_rejected(scene, tmp_path):
    # SUPPRESSANT_DROP with no THERMAL_RECON predecessor -> E_WORKFLOW
    bad = tmp_path / "X2.yaml"
    bad.write_text(
        "id: X2\nfamily: C\nprofile: SELECTIVE_RESPONSE\n"
        "command: x\nrationale: x\n"
        "allowed_graphs:\n"
        "  - tasks:\n"
        "      - {task_type: SUPPRESSANT_DROP, target: FIRE_SITE_1, priority: 9}\n"
        "    edges: []\n"
    )
    with pytest.raises(ValueError, match="fails the Validator"):
        load_annotation(bad, scene)


# -- metrics --------------------------------------------------------


def _k(tt, target):
    return (TaskType(tt), target)


def test_prf_math():
    p = PRF(tp=3, fp=1, fn=2)
    assert p.precision == 0.75
    assert p.recall == 0.6
    assert abs(p.f1 - (2 * 0.75 * 0.6) / (0.75 + 0.6)) < 1e-9


def test_score_graph_exact_match():
    ref = RefGraph(
        tasks=frozenset({_k("AREA_RECON", "ZONE_A"), _k("THERMAL_RECON", "FIRE_SITE_1")}),
        edges=frozenset(),
    )
    cand = MissionCandidate.from_raw(
        {
            "tasks": [
                {"task_type": "AREA_RECON", "target": "ZONE_A", "priority": 5},
                {"task_type": "THERMAL_RECON", "target": "FIRE_SITE_1", "priority": 9},
            ],
            "edges": [],
        }
    )[0]
    s = score_graph(cand, (ref,))
    assert s.exact_match
    assert s.tasks.precision == 1.0 and s.tasks.recall == 1.0


def test_score_graph_counts_extra_and_missing():
    ref = RefGraph(
        tasks=frozenset({_k("AREA_RECON", "ZONE_A"), _k("AREA_RECON", "ZONE_B")}),
        edges=frozenset(),
    )
    cand = MissionCandidate.from_raw(
        {
            "tasks": [
                {"task_type": "AREA_RECON", "target": "ZONE_A", "priority": 5},
                {"task_type": "AREA_RECON", "target": "ZONE_C", "priority": 5},
            ],
            "edges": [],
        }
    )[0]
    s = score_graph(cand, (ref,))
    assert not s.exact_match
    assert s.tasks.tp == 1 and s.tasks.fp == 1 and s.tasks.fn == 1


def test_score_graph_picks_best_matching_allowed_reference():
    small = RefGraph(tasks=frozenset({_k("AREA_RECON", "ZONE_A")}), edges=frozenset())
    big = RefGraph(
        tasks=frozenset(
            {_k("AREA_RECON", "ZONE_A"), _k("AREA_RECON", "ZONE_B"), _k("AREA_RECON", "ZONE_C")}
        ),
        edges=frozenset(),
    )
    cand = MissionCandidate.from_raw(
        {
            "tasks": [
                {"task_type": "AREA_RECON", "target": "ZONE_A", "priority": 5},
                {"task_type": "AREA_RECON", "target": "ZONE_B", "priority": 5},
                {"task_type": "AREA_RECON", "target": "ZONE_C", "priority": 5},
            ],
            "edges": [],
        }
    )[0]
    s = score_graph(cand, (small, big))
    assert s.ref_index == 1 and s.exact_match


# -- harness end to end -------------------------------------------


def _perfect_script(annotations, scene):
    """Flat MockBackend script: Step1 + Step2 per case, from the canonical ref."""
    script: list = []
    for ann in annotations:
        g = ann.allowed_graphs[0]
        tasks = []
        for tt, target in sorted(g.tasks, key=lambda k: (k[0].value, k[1])):
            prio = scene.incidents[target].priority if target in scene.incidents else 5
            tasks.append(LLMTask(task_type=tt.value, target=target, priority=prio))
        edges = [
            LLMEdge(predecessor=f"{p[0].value}:{p[1]}", successor=f"{s[0].value}:{s[1]}")
            for p, s in sorted(g.edges, key=lambda e: (e[0][0].value, e[0][1]))
        ]
        script.append(Step1Output(tasks=tasks))
        script.append(Step2Output(edges=edges))
    return script


def test_harness_all_perfect(scene, annotations):
    backend = MockBackend(_perfect_script(annotations, scene))
    run = run_all(scene, backend, annotations=annotations)

    c = run.counts()
    assert c == {
        "n": 9,
        "schema_valid": 9,
        "raw_whole_graph_valid": 9,
        "repaired_whole_graph_valid": 0,
        "approved": 9,
    }
    final = run.axis("final")
    assert final.scored == 9 and final.exact_match == 9
    assert final.task_micro.fp == 0 and final.task_micro.fn == 0
    assert final.edge_micro.fp == 0 and final.edge_micro.fn == 0
    assert run.validator_version and run.scene_hash
    assert run.backend_kind == "MockBackend"


def test_harness_records_reproducibility_and_family_breakdown(scene, annotations):
    backend = MockBackend(_perfect_script(annotations, scene))
    run = run_all(scene, backend, annotations=annotations)
    fam = run.by_family()
    assert fam["A"]["n"] == 3 and fam["A"]["approved"] == 3
    assert fam["B"]["n"] == 3 and fam["C"]["n"] == 3
    d = to_dict(run)
    assert d["meta"]["validator_version"] == run.validator_version
    assert d["meta"]["scene_hash"] == run.scene_hash
    assert len(d["cases"]) == 9
    assert "P6" in text_report(run)


def test_harness_imperfect_case_is_scored_not_crashed(scene, annotations):
    a1 = [a for a in annotations if a.id == "A1"][0]
    g = a1.allowed_graphs[0]
    # keep the full incident workflow (so it stays whole-graph-valid) but omit
    # one zone recon -> valid, not an exact match.
    keys = [k for k in g.tasks if k != (TaskType.AREA_RECON, "ZONE_D")]
    tasks = [
        LLMTask(
            task_type=tt.value,
            target=target,
            priority=scene.incidents[target].priority if target in scene.incidents else 5,
        )
        for tt, target in keys
    ]
    edges = [
        LLMEdge(predecessor=f"{p[0].value}:{p[1]}", successor=f"{s[0].value}:{s[1]}")
        for p, s in g.edges
    ]
    backend = MockBackend([Step1Output(tasks=tasks), Step2Output(edges=edges)])
    run = run_all(scene, backend, annotations=[a1])
    case = run.cases[0]
    assert case.approved and case.raw_whole_graph_valid
    assert case.final_score is not None
    assert case.final_score.tasks.fn == 1
    assert not case.final_score.exact_match


def test_harness_schema_failure_leaves_score_none(scene, annotations):
    a1 = [a for a in annotations if a.id == "A1"][0]
    bad = {"tasks": [{"task_type": "AREA_RECON", "target": "ZONE_A", "priority": 3, "x": 1}]}
    run = run_all(scene, MockBackend([bad]), annotations=[a1])
    case = run.cases[0]
    assert not case.approved and case.failure_category == "SCHEMA"
    assert case.raw_score is None and case.final_score is None
    assert run.axis("final").scored == 0


def test_harness_survives_a_raising_backend(scene, annotations):
    class Boom:
        def complete(self, *a, **k):
            raise RuntimeError("network down")

    run = run_all(scene, Boom(), annotations=annotations[:2])
    assert all(c.failure_category.startswith("HARNESS_ERROR") for c in run.cases)
    assert run.counts()["approved"] == 0
