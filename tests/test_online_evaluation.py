"""P9.4 frozen-fixture comparison gates (§19.5)."""

import pytest
import yaml

from evaluation.online_reallocation import (
    _DEFAULT_FIXTURE,
    load_online_fixture,
    run_comparison,
    text_report,
    to_json,
)


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


# -- strict fixture schema (§19.5, D-041) ---------------------------------


def _fixture_dict():
    return yaml.safe_load(_DEFAULT_FIXTURE.read_text(encoding="utf-8"))


def _write(tmp_path, raw):
    path = tmp_path / "fixture.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return path


def test_the_frozen_fixture_still_loads(tmp_path):
    assert load_online_fixture(_write(tmp_path, _fixture_dict())).fixture_id == (
        "P9_REPRESENTATIVE_1"
    )


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("fixture_id", 12345),           # an int must not become "12345"
        ("fixture_id", "   "),
        ("base_scene", 7),
        ("online_report_zone", 7),
        ("expected_new_incident_id", 6),
        ("online_update_up_to", "NOT_A_WORKFLOW_STEP"),
        ("initial_report_zones", ["ZONE_C", 4]),
        ("initial_report_zones", "ZONE_C"),
    ],
)
def test_a_mistyped_fixture_field_is_refused_at_load(tmp_path, key, value):
    raw = _fixture_dict()
    raw[key] = value
    with pytest.raises(ValueError):
        load_online_fixture(_write(tmp_path, raw))


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("simulation_time", "121.64323236970407"),  # a str must not become a float
        ("simulation_time", True),                  # bool is not a number here
        ("simulation_time", float("inf")),
        ("simulation_time", float("nan")),
        ("completed_now", [1]),
        ("completed_now", "SUPPRESSANT_DROP__FIRE_SITE_3"),
    ],
)
def test_a_mistyped_checkpoint_field_is_refused_at_load(tmp_path, key, value):
    raw = _fixture_dict()
    raw["expected_checkpoint"][key] = value
    with pytest.raises(ValueError):
        load_online_fixture(_write(tmp_path, raw))


def test_a_mistyped_expected_release_entry_is_refused(tmp_path):
    raw = _fixture_dict()
    raw["expected_release"]["selective"] = [1]
    with pytest.raises(ValueError):
        load_online_fixture(_write(tmp_path, raw))


# -- suffix reporting (§19.5, D-041) --------------------------------------


def test_suffix_extra_release_count_is_zero_for_selective_and_null_elsewhere():
    runs = {run.policy: run for run in run_comparison().policies}

    # The honest headline: the §19.3 suffix step never fired on this fixture.
    assert runs["selective"].suffix_extra_release_count == 0
    assert set(runs["selective"].released_tasks) == set(
        runs["selective"].directly_affected_tasks
    )
    # Undefined for the other two: full-reset drops every unstarted assignment
    # regardless of bundles, so the same subtraction is not a suffix effect.
    assert runs["no-reset"].suffix_extra_release_count is None
    assert runs["full-reset"].suffix_extra_release_count is None


def test_the_report_states_the_suffix_count_rather_than_hiding_it():
    report = text_report(run_comparison())
    assert "suffix_extra_release_count=0" in report
    assert "suffix_extra_release_count=n/a" in report
