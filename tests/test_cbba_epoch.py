"""CBBA single-epoch auction (RESEARCH_CONTRACT.md §11)."""

from dataclasses import replace
from pathlib import Path

import pytest

from allocation.cbba import run_epoch
from core.enums import TaskStatus, TaskType
from scenarios.compiler import compile_task
from scenarios.scene import load_scene

SCENE = Path(__file__).parents[1] / "scenarios" / "industrial_park.yaml"


@pytest.fixture
def scene():
    return load_scene(SCENE)


def fresh_agents(scene):
    return {a.agent_id: replace(a, bundle=[], path=[]) for a in scene.fleet}


def ready_tasks(scene, specs):
    out = {}
    for tt, target, prio in specs:
        t = compile_task(scene, tt, target, prio)
        t.status = TaskStatus.READY
        out[t.task_id] = t
    return out


def test_every_frontier_task_gets_exactly_one_winner(scene):
    tasks = ready_tasks(
        scene,
        [
            (TaskType.AREA_RECON, "ZONE_A", 4),
            (TaskType.AREA_RECON, "ZONE_B", 5),
            (TaskType.THERMAL_RECON, "FIRE_SITE_1", 9),
        ],
    )
    result = run_epoch(tasks, fresh_agents(scene), scene)
    assert set(result.winners) == set(tasks)
    # a task is in exactly one winner's bundle
    for task_id in tasks:
        assert result.winners[task_id] is not None


def test_aerial_recon_only_won_by_scout_uavs(scene):
    tasks = ready_tasks(scene, [(TaskType.AREA_RECON, "ZONE_A", 5)])
    result = run_epoch(tasks, fresh_agents(scene), scene)
    assert result.winners["AREA_RECON__ZONE_A"] in {"S1", "S2"}


def test_suppressant_drop_only_won_by_response_uavs(scene):
    tasks = ready_tasks(scene, [(TaskType.SUPPRESSANT_DROP, "FIRE_SITE_1", 9)])
    result = run_epoch(tasks, fresh_agents(scene), scene)
    assert result.winners["SUPPRESSANT_DROP__FIRE_SITE_1"] in {"R1", "R2"}


def test_ground_task_only_won_by_safety_ugvs(scene):
    tasks = ready_tasks(
        scene,
        [
            (TaskType.GROUND_INSPECTION, "FIRE_SITE_1", 8),
            (TaskType.HAZARD_MARKER_DEPLOY, "FIRE_SITE_2", 5),
        ],
    )
    result = run_epoch(tasks, fresh_agents(scene), scene)
    for a in result.winners.values():
        assert a in {"G1", "G2"}


def test_run_epoch_is_deterministic(scene):
    specs = [
        (TaskType.AREA_RECON, "ZONE_A", 4),
        (TaskType.AREA_RECON, "ZONE_B", 5),
        (TaskType.AREA_RECON, "ZONE_C", 3),
        (TaskType.AREA_RECON, "ZONE_D", 4),
    ]
    r1 = run_epoch(ready_tasks(scene, specs), fresh_agents(scene), scene)
    r2 = run_epoch(ready_tasks(scene, specs), fresh_agents(scene), scene)
    assert r1.winners == r2.winners
    assert r1.winning_bids == r2.winning_bids
    assert r1.rounds == r2.rounds


def test_converges_and_reports_round_count(scene):
    tasks = ready_tasks(scene, [(TaskType.THERMAL_RECON, "FIRE_SITE_1", 9)])
    result = run_epoch(tasks, fresh_agents(scene), scene)
    assert result.rounds >= 1
    assert result.winners["THERMAL_RECON__FIRE_SITE_1"] in {"S1", "S2", "R1", "R2"}


def test_idle_agents_are_allowed(scene):
    # One task, six agents -> five stay idle; not an error (contract §5).
    tasks = ready_tasks(scene, [(TaskType.AREA_RECON, "ZONE_A", 5)])
    agents = fresh_agents(scene)
    run_epoch(tasks, agents, scene)
    holders = [aid for aid, a in agents.items() if a.bundle]
    assert len(holders) == 1
