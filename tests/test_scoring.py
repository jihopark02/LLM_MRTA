"""CBBA scoring (RESEARCH_CONTRACT.md §11), ported + platform-aware."""

from pathlib import Path

import pytest

from allocation.scoring import DEFAULT_LAMBDA, marginal_score, path_score, reward
from core.enums import TaskType
from scenarios.compiler import compile_task
from scenarios.scene import load_scene

SCENE = Path(__file__).parents[1] / "scenarios" / "industrial_park.yaml"


@pytest.fixture(scope="module")
def scene():
    return load_scene(SCENE)


def ag(scene, aid):
    return next(a for a in scene.fleet if a.agent_id == aid)


def task(scene, tt, target, prio):
    return compile_task(scene, tt, target, prio)


def test_reward_is_priority_not_scaled(scene):
    assert reward(task(scene, TaskType.AREA_RECON, "ZONE_A", 7)) == 7.0


def test_empty_path_scores_zero(scene):
    assert path_score(ag(scene, "S1"), [], scene) == 0.0


def test_path_score_discounts_later_tasks(scene):
    s1 = ag(scene, "S1")
    near = task(scene, TaskType.AREA_RECON, "ZONE_C", 5)  # closer to depot
    far = task(scene, TaskType.AREA_RECON, "ZONE_A", 5)  # farther
    assert path_score(s1, [near], scene) > path_score(s1, [far], scene)


def test_marginal_score_negative_inf_for_ineligible_platform(scene):
    g1 = ag(scene, "G1")  # UGV
    aerial = task(scene, TaskType.AREA_RECON, "ZONE_A", 5)  # UAV-only
    gain, n = marginal_score(g1, aerial, [], scene)
    assert gain == float("-inf") and n == -1


def test_marginal_score_negative_inf_for_missing_capability(scene):
    s1 = ag(scene, "S1")  # AERIAL_RECON + THERMAL_SENSOR, no SUPPRESSANT_PAYLOAD
    drop = task(scene, TaskType.SUPPRESSANT_DROP, "FIRE_SITE_1", 9)
    gain, _ = marginal_score(s1, drop, [], scene)
    assert gain == float("-inf")


def test_marginal_score_zero_when_task_already_in_path(scene):
    s1 = ag(scene, "S1")
    t = task(scene, TaskType.AREA_RECON, "ZONE_A", 5)
    assert marginal_score(s1, t, [t], scene) == (0.0, -1)


def test_marginal_score_picks_best_insertion(scene):
    s1 = ag(scene, "S1")
    a = task(scene, TaskType.AREA_RECON, "ZONE_A", 5)
    c = task(scene, TaskType.AREA_RECON, "ZONE_C", 5)
    d = task(scene, TaskType.AREA_RECON, "ZONE_D", 5)
    gain, n = marginal_score(s1, d, [c, a], scene)
    assert gain > float("-inf")
    assert 0 <= n <= 2


def test_lambda_default_is_the_fixed_value():
    assert DEFAULT_LAMBDA == 0.999
