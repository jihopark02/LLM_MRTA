"""P12.4 counterfactual annotation, scoring, and raw-audit gates."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from evaluation.incident_contingency import (
    load_annotation,
    mock_backend_factory,
    run_counterfactual,
    to_json,
)

ROOT = Path(__file__).parents[1]
ANNOTATION = ROOT / "data" / "p12_counterfactual.yaml"


def test_precommitted_counterfactual_has_all_policy_depths_and_two_zones():
    annotation = load_annotation(ANNOTATION)

    assert [case.expected_policy for case in annotation.policy_cases] == [
        None,
        "THERMAL_RECON",
        "SUPPRESSANT_DROP",
        "GROUND_INSPECTION",
        "GROUND_SUPPRESSION",
    ]
    assert [len(case.expected_response_tasks) for case in annotation.policy_cases] == [
        0,
        1,
        2,
        3,
        4,
    ]
    assert {case.expected_zone for case in annotation.report_cases} == {
        "ZONE_A",
        "ZONE_D",
    }
    assert len(annotation.unsupported_cases) == 1


def test_mock_self_test_is_eight_of_eight_and_retains_raw_session_audits():
    annotation = load_annotation(ANNOTATION)
    run = run_counterfactual(
        annotation,
        mock_backend_factory(annotation),
        requested_model=None,
    )

    assert run.exact_count == len(run.cases) == 8
    assert {case.termination for case in run.cases if case.family != "unsupported"} == {
        "COMPLETED"
    }
    assert all(not case.capability_violations for case in run.cases)
    assert all(not case.precedence_violations for case in run.cases)
    assert all(case.session_audit["events"] for case in run.cases)
    policies = [
        case.actual["policy"] for case in run.cases if case.family == "policy"
    ]
    assert policies == [
        None,
        "THERMAL_RECON",
        "SUPPRESSANT_DROP",
        "GROUND_INSPECTION",
        "GROUND_SUPPRESSION",
    ]

    reports = [case for case in run.cases if case.family == "operator-report"]
    assert reports[0].actual["zone"] != reports[1].actual["zone"]
    assert (
        reports[0].session_audit["scene_hash"]
        != reports[1].session_audit["scene_hash"]
    )
    assert '"resolved_models"' in to_json(run)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda raw: raw.update(extra="not allowed"),
        lambda raw: raw.update(annotation_version="p11"),
        lambda raw: raw["policy_cases"][0].update(expected_response_tasks="none"),
        lambda raw: raw["report_cases"][0].update(expected_zone=True),
    ],
)
def test_counterfactual_annotation_is_strict(tmp_path, mutate):
    raw = yaml.safe_load(ANNOTATION.read_text(encoding="utf-8"))
    mutate(raw)
    path = tmp_path / "counterfactual.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    with pytest.raises((ValidationError, ValueError)):
        load_annotation(path)

