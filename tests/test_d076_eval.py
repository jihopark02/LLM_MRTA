"""D-076 held-out evaluation gate (RESEARCH_CONTRACT §18.15, DECISIONS S12).

The annotation set is fixed before any live run; this gate proves it is
internally consistent (the deterministic resolver + compiler reproduce every
annotated `resolved` / graph) and that the fail-closed and counterfactual
cases behave as designed. The live scoring itself is not a unit test.
"""

from pathlib import Path

import pytest
import yaml

from evaluation.d076_eval import (
    LEVELS,
    gold_backend,
    load_all,
    load_case,
    run_eval,
    summarise,
    text_report,
    to_json,
)

ROOT = Path(__file__).parents[1]


@pytest.fixture(scope="module")
def cases():
    return load_all()


@pytest.fixture(scope="module")
def gold_run(cases):
    return run_eval(cases, gold_backend, "mock")


def test_the_set_is_45_cases_15_per_level(cases):
    assert len(cases) == 45
    for level in LEVELS:
        assert sum(c.level == level for c in cases) == 15


def test_every_level_has_fail_closed_cases(cases):
    for level in LEVELS:
        fail_closed = [
            c for c in cases
            if c.level == level and c.expected_outcome in {"CLARIFICATION", "REJECTED"}
        ]
        assert len(fail_closed) >= 3, level
        reasons = {c.expected_reason for c in fail_closed}
        # not all the same trivial reason
        assert len(reasons) >= 2, (level, reasons)


def test_contextual_has_at_least_three_counterfactual_pairs(cases):
    pairs = [c for c in cases if c.counterfactual_of]
    assert len(pairs) >= 3
    by_id = {c.id: c for c in cases}
    for case in pairs:
        base = by_id[case.counterfactual_of]
        assert case.utterance == base.utterance                 # same words
        # different world -> different resolved targets
        assert case.expected_resolved != base.expected_resolved


def test_gold_backend_reproduces_every_annotation(gold_run):
    s = summarise(gold_run)["overall"]
    assert s["ir_exact"] == {"n": 45, "d": 45, "pct": 100.0}
    assert s["resolved_exact"] == {"n": 45, "d": 45, "pct": 100.0}
    assert s["graph_exact"] == {"n": 45, "d": 45, "pct": 100.0}
    assert s["outcome_correct"] == {"n": 45, "d": 45, "pct": 100.0}
    assert s["unsafe_commits"] == 0
    assert s["attribution"] == {
        "all_correct": 45, "ir_wrong": 0, "resolver_wrong": 0, "compiler_wrong": 0
    }


def test_gold_backend_counterfactual_pairs_diverge(gold_run):
    cf = summarise(gold_run)["counterfactual_pairs"]
    assert cf["total"] >= 3
    assert cf["diverged"] == cf["total"]


def test_fail_closed_cases_commit_nothing_under_gold(gold_run):
    for score in gold_run.scores:
        expected = {c.id: c for c in load_all()}[score.id].expected_outcome
        if expected in {"CLARIFICATION", "REJECTED"}:
            assert score.actual_outcome != "COMMITTED"
            assert not score.unsafe_commit
            assert score.graph_exact  # "nothing committed" is the graph check here


def test_loader_rejects_a_resolved_that_disagrees_with_the_resolver(tmp_path):
    src = ROOT / "data" / "d076_eval" / "explicit" / "E01.yaml"
    raw = yaml.safe_load(src.read_text())
    raw["expected"]["resolved"]["recon"] = [["ZONE_A", "ZONE_B"]]  # E01 is only ZONE_A
    bad = tmp_path / "explicit"
    bad.mkdir()
    (bad / "E01.yaml").write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False))

    with pytest.raises(ValueError, match="resolved"):
        load_case(bad / "E01.yaml")


def test_loader_rejects_a_committed_case_whose_ir_actually_clarifies(tmp_path):
    src = ROOT / "data" / "d076_eval" / "explicit" / "E13.yaml"  # a CLARIFICATION case
    raw = yaml.safe_load(src.read_text())
    raw["expected"]["outcome"] = "COMMITTED"
    del raw["expected"]["clarification_reason"]
    bad = tmp_path / "explicit"
    bad.mkdir()
    (bad / "E13.yaml").write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False))

    with pytest.raises(ValueError, match="resolver clarified"):
        load_case(bad / "E13.yaml")


def test_report_and_json_are_serialisable(gold_run):
    report = text_report(gold_run)
    assert "D-076 held-out evaluation" in report
    assert "counterfactual pairs: 3/3" in report
    import json

    payload = json.loads(to_json(gold_run))
    assert len(payload["cases"]) == 45
    assert payload["summary"]["overall"]["unsafe_commits"] == 0
