"""P9.4 frozen-fixture comparison gates (§19.5)."""

from evaluation.online_reallocation import run_comparison, text_report, to_json


def test_frozen_fixture_distinguishes_all_three_policies_and_finishes_cleanly():
    result = run_comparison()
    runs = {run.policy: run for run in result.policies}

    assert result.checkpoint_event == 10
    assert result.completed_now == ("SUPPRESSANT_DROP__FIRE_SITE_3",)
    assert result.new_incident_id == "FIRE_SITE_6"
    assert runs["no-reset"].released_tasks == ()
    assert runs["selective"].released_tasks == ("AREA_RECON__ZONE_C",)
    assert runs["full-reset"].released_tasks == (
        "AREA_RECON__ZONE_C",
        "GROUND_INSPECTION__FIRE_SITE_1",
    )
    assert len(runs["selective"].preserved_assigned_tasks) > len(
        runs["full-reset"].preserved_assigned_tasks
    )
    assert all(run.termination == "COMPLETED" for run in runs.values())
    assert all(not run.capability_violations for run in runs.values())
    assert all(not run.precedence_violations for run in runs.values())


def test_comparison_is_deterministic_and_serialisable():
    first = run_comparison()
    second = run_comparison()

    assert first == second
    assert to_json(first) == to_json(second)
    assert "selective" in text_report(first)
