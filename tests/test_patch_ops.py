"""MissionPatch raw op-list validation (RESEARCH_CONTRACT.md §10 step 2, D-005)."""

from pathlib import Path

import pytest

from core.enums import TaskType
from scenarios.fixture import load_reference_fixture
from validator.errors import ErrorCode
from validator.patch import (
    AddEdge,
    AddTask,
    MissionPatch,
    RemoveEdge,
    post_patch_keys,
    validate_patch_ops,
)

TR_F1 = (TaskType.THERMAL_RECON, "FIRE_SITE_1")
SD_F1 = (TaskType.SUPPRESSANT_DROP, "FIRE_SITE_1")
GI_F1 = (TaskType.GROUND_INSPECTION, "FIRE_SITE_1")
HM_F1 = (TaskType.HAZARD_MARKER_DEPLOY, "FIRE_SITE_1")


@pytest.fixture(scope="module")
def base():
    return load_reference_fixture(
        Path(__file__).parents[1] / "scenarios" / "reference_fixture.yaml"
    ).graph


def codes(errs):
    return sorted({e.code for e in errs})


def test_clean_rewire_patch_passes_op_validation(base):
    # RQ3-style: remove one edge, add two new ones for a new task.
    patch = MissionPatch(
        [
            RemoveEdge(SD_F1, GI_F1),
            AddTask(TaskType.THERMAL_RECON, "FIRE_SITE_1_RECHECK", 9),
            AddEdge(SD_F1, (TaskType.THERMAL_RECON, "FIRE_SITE_1_RECHECK")),
            AddEdge((TaskType.THERMAL_RECON, "FIRE_SITE_1_RECHECK"), GI_F1),
        ]
    )
    assert validate_patch_ops(patch, base) == []


def test_add_and_remove_same_edge_conflicts(base):
    patch = MissionPatch([AddEdge(TR_F1, HM_F1), RemoveEdge(TR_F1, HM_F1)])
    assert codes(validate_patch_ops(patch, base)) == [ErrorCode.E_PATCH_CONFLICT]


def test_duplicate_add_edge_conflicts(base):
    patch = MissionPatch([AddEdge(TR_F1, HM_F1), AddEdge(TR_F1, HM_F1)])
    assert codes(validate_patch_ops(patch, base)) == [ErrorCode.E_PATCH_CONFLICT]


def test_remove_nonexistent_edge_conflicts(base):
    patch = MissionPatch([RemoveEdge(TR_F1, GI_F1)])  # not an edge in the fixture
    assert codes(validate_patch_ops(patch, base)) == [ErrorCode.E_PATCH_CONFLICT]


def test_add_existing_edge_conflicts(base):
    patch = MissionPatch([AddEdge(TR_F1, SD_F1)])  # already in the fixture
    assert codes(validate_patch_ops(patch, base)) == [ErrorCode.E_PATCH_CONFLICT]


def test_add_task_duplicating_existing_conflicts(base):
    patch = MissionPatch([AddTask(TaskType.THERMAL_RECON, "FIRE_SITE_1", 9)])
    assert codes(validate_patch_ops(patch, base)) == [ErrorCode.E_PATCH_CONFLICT]


def test_unknown_op_is_schema_error(base):
    patch = MissionPatch(["not an op"])
    assert ErrorCode.E_SCHEMA in codes(validate_patch_ops(patch, base))


def test_post_patch_keys_is_order_independent(base):
    ops = [
        RemoveEdge(SD_F1, GI_F1),
        AddTask(TaskType.THERMAL_RECON, "FIRE_SITE_1_RECHECK", 9),
        AddEdge(SD_F1, (TaskType.THERMAL_RECON, "FIRE_SITE_1_RECHECK")),
        AddEdge((TaskType.THERMAL_RECON, "FIRE_SITE_1_RECHECK"), GI_F1),
    ]
    a_nodes, a_edges = post_patch_keys(MissionPatch(ops), base)
    b_nodes, b_edges = post_patch_keys(MissionPatch(list(reversed(ops))), base)
    assert sorted(a_nodes) == sorted(b_nodes)
    assert a_edges == b_edges
    assert (SD_F1, GI_F1) not in a_edges
    assert (SD_F1, (TaskType.THERMAL_RECON, "FIRE_SITE_1_RECHECK")) in a_edges
