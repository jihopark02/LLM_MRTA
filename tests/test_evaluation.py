"""P6 gate (RESEARCH_CONTRACT.md §12, §15, D-021, D-022): evaluation harness.

The metrics are unit-tested directly; the harness is exercised end to end with
a ``MockBackend`` — no network, no API key — driving perfect, imperfect and
schema-broken cases. priority is scene-derived (D-022); candidates and
annotations carry task_type + target only.
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
    assert [a.id for a in annotations] == ["A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2", "C3"]
    assert [a.family for a in annotations] == list("AAABBBCCC")
    for a in (x for x in annotations if x.family == "A"):  # == the P1 reference fixture shape
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
        "      - {task_type: SUPPRESSANT_DROP, target: FIRE_SITE_1}\n"
        "    edges: []\n"
    )
    with pytest.raises(ValueError, match="fails the Validator"):
        load_annotation(bad, scene)


def test_annotation_explicit_task_with_priority_key_is_rejected(scene, tmp_path):
    bad = tmp_path / "X3.yaml"
    bad.write_text(
        "id: X3\nfamily: C\nprofile: SELECTIVE_RESPONSE\n"
        "command: x\nrationale: x\n"
        "allowed_graphs:\n"
        "  - tasks:\n"
        "      - {task_type: THERMAL_RECON, target: FIRE_SITE_1, priority: 9}\n"
        "    edges: []\n"
    )
    with pytest.raises(ValueError, match=r"\{task_type, target\}"):
        load_annotation(bad, scene)


# -- metrics --------------------------------------------------------


def _k(tt, target):
    return (TaskType(tt), target)


def _cand(*task_pairs, edges=()):
    return MissionCandidate.from_raw(
        {
            "tasks": [{"task_type": tt, "target": tgt} for tt, tgt in task_pairs],
            "edges": [list(e) for e in edges],
        }
    )[0]


def test_prf_math():
    p = PRF(tp=3, fp=1, fn=2)
    assert p.precision == 0.75
    assert p.recall == 0.6
    assert p.defined
    assert abs(p.f1 - (2 * 0.75 * 0.6) / (0.75 + 0.6)) < 1e-9


def test_prf_empty_is_undefined():
    assert not PRF(0, 0, 0).defined


def test_score_graph_exact_match():
    ref = RefGraph(
        tasks=frozenset({_k("AREA_RECON", "ZONE_A"), _k("THERMAL_RECON", "FIRE_SITE_1")}),
        edges=frozenset(),
    )
    s = score_graph(_cand(("AREA_RECON", "ZONE_A"), ("THERMAL_RECON", "FIRE_SITE_1")), (ref,))
    assert s.exact_match
    assert s.tasks.precision == 1.0 and s.tasks.recall == 1.0


def test_score_graph_counts_extra_and_missing():
    ref = RefGraph(
        tasks=frozenset({_k("AREA_RECON", "ZONE_A"), _k("AREA_RECON", "ZONE_B")}),
        edges=frozenset(),
    )
    s = score_graph(_cand(("AREA_RECON", "ZONE_A"), ("AREA_RECON", "ZONE_C")), (ref,))
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
    cand = _cand(
        ("AREA_RECON", "ZONE_A"), ("AREA_RECON", "ZONE_B"), ("AREA_RECON", "ZONE_C")
    )
    s = score_graph(cand, (small, big))
    assert s.ref_index == 1 and s.exact_match


def test_score_graph_edge_prf_is_undefined_when_no_edges_either_side():
    ref = RefGraph(tasks=frozenset({_k("THERMAL_RECON", "FIRE_SITE_1")}), edges=frozenset())
    s = score_graph(_cand(("THERMAL_RECON", "FIRE_SITE_1")), (ref,))
    assert not s.edges.defined


# -- harness end to end -------------------------------------------


def _perfect_script(annotations):
    """Flat MockBackend script: Step1 + Step2 per case, from the canonical ref."""
    script: list = []
    for ann in annotations:
        g = ann.allowed_graphs[0]
        tasks = [
            LLMTask(task_type=tt.value, target=target)
            for tt, target in sorted(g.tasks, key=lambda k: (k[0].value, k[1]))
        ]
        edges = [
            LLMEdge(predecessor=f"{p[0].value}:{p[1]}", successor=f"{s[0].value}:{s[1]}")
            for p, s in sorted(g.edges, key=lambda e: (e[0][0].value, e[0][1]))
        ]
        script += [Step1Output(tasks=tasks), Step2Output(edges=edges)]
    return script


def test_harness_all_perfect(scene, annotations):
    run = run_all(scene, MockBackend(_perfect_script(annotations)), annotations=annotations)

    assert run.counts() == {
        "n": 9,
        "schema_valid": 9,
        "raw_whole_graph_valid": 9,
        "approved": 9,
        "harness_errors": 0,
    }
    assert run.repair_counts() == {"attempted": 0, "recovered": 0, "first_pass_approved": 9}
    final = run.axis("final")
    assert final.scored == 9 and final.exact_match == 9
    assert final.task_micro.fp == 0 and final.task_micro.fn == 0
    assert final.edge_micro.fp == 0 and final.edge_micro.fn == 0
    assert run.validator_version == "1.3" and run.scene_hash
    assert run.backend_kind == "MockBackend"


def test_harness_audit_snapshot_has_recomputable_contents(scene, annotations):
    a1 = next(a for a in annotations if a.id == "A1")
    run = run_all(scene, MockBackend(_perfect_script([a1])), annotations=[a1])
    case = run.cases[0]
    assert case.final is not None
    assert len(case.final.tasks) == 12 and len(case.final.edges) == 6
    # priority is carried in the audit snapshot, scene-derived
    prio = {(t["task_type"], t["target"]): t["priority"] for t in case.final.tasks}
    assert prio[("THERMAL_RECON", "FIRE_SITE_1")] == 9
    assert prio[("GROUND_INSPECTION", "FIRE_SITE_2")] == 7
    assert prio[("AREA_RECON", "ZONE_A")] == 4
    assert case.final.accepted and case.final.error_codes == []
    assert len(case.final.graph_hash) == 64

    d = to_dict(run)
    # a third party recomputes exact-match from task_type/target alone
    got_tasks = {(t["task_type"], t["target"]) for t in d["cases"][0]["final"]["tasks"]}
    ref_tasks = {(tt.value, tgt) for tt, tgt in a1.allowed_graphs[0].tasks}
    assert got_tasks == ref_tasks


def test_harness_records_family_breakdown_and_report(scene, annotations):
    run = run_all(scene, MockBackend(_perfect_script(annotations)), annotations=annotations)
    fam = run.by_family()
    assert fam["A"]["n"] == 3 and fam["A"]["approved"] == 3
    assert fam["B"]["n"] == 3 and fam["C"]["n"] == 3
    # family B has no reference edges -> edge P/R is N/A, not 1.0
    assert fam["B"]["final"].edge_precision_mean is None
    assert fam["A"]["final"].edge_precision_mean == 1.0
    report = text_report(run)
    assert "P6" in report and "#1-#12" in report and "N/A" in report


def test_harness_imperfect_case_is_scored_not_crashed(scene, annotations):
    a1 = next(a for a in annotations if a.id == "A1")
    g = a1.allowed_graphs[0]
    # keep the full incident workflow but omit one zone recon -> valid, not exact.
    keys = [k for k in g.tasks if k != (TaskType.AREA_RECON, "ZONE_D")]
    tasks = [LLMTask(task_type=tt.value, target=target) for tt, target in keys]
    edges = [
        LLMEdge(predecessor=f"{p[0].value}:{p[1]}", successor=f"{s[0].value}:{s[1]}")
        for p, s in g.edges
    ]
    backend = MockBackend([Step1Output(tasks=tasks), Step2Output(edges=edges)])
    case = run_all(scene, backend, annotations=[a1]).cases[0]
    assert case.approved and case.raw_whole_graph_valid
    assert case.final_score is not None and case.final_score.tasks.fn == 1
    assert not case.final_score.exact_match


def test_harness_schema_failure_leaves_score_none(scene, annotations):
    a1 = next(a for a in annotations if a.id == "A1")
    bad = {"tasks": [{"task_type": "AREA_RECON", "target": "ZONE_A", "x": 1}]}
    case = run_all(scene, MockBackend([bad]), annotations=[a1]).cases[0]
    assert not case.approved and case.failure_category == "SCHEMA"
    assert case.harness_error is None
    assert case.raw is None and case.final is None
    assert case.raw_score is None and case.final_score is None


def test_harness_survives_a_raising_backend(scene, annotations):
    class Boom:
        def complete(self, *a, **k):
            raise RuntimeError("network down")

    run = run_all(scene, Boom(), annotations=annotations[:2])
    for c in run.cases:
        assert c.harness_error is not None and "network down" in c.harness_error
        assert c.failure_category is None  # kept separate from model-output failures
    assert run.counts()["approved"] == 0 and run.counts()["harness_errors"] == 2


# -- figure ------------------------------------------------------


def test_plots_write_png_and_pdf(scene, annotations, tmp_path):
    pytest.importorskip("matplotlib")
    from evaluation.plots import save

    run = run_all(scene, MockBackend(_perfect_script(annotations)), annotations=annotations)
    out = save(run, tmp_path / "fig")
    assert [p.suffix for p in out] == [".png", ".pdf"]
    assert all(p.exists() and p.stat().st_size > 0 for p in out)
