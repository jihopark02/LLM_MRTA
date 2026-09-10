"""D-076: deterministic Mission Compiler — ResolvedMissionIR → graph / patch."""

from pathlib import Path

import pytest

from core.enums import TaskType
from interaction.compile_clauses import compile_new_graph, compile_patch
from interaction.resolve import (
    ResolvedMissionIR,
    ResolvedReconClause,
    ResolvedResponseClause,
)
from scenarios.compiler import compile_reference_graph
from scenarios.scene import load_scene
from validator.candidate import MissionCandidate
from validator.patch import AddEdge, AddTask
from validator.validate import validate_candidate

SCENE = Path(__file__).parents[1] / "scenarios" / "industrial_park.yaml"


@pytest.fixture
def scene():
    return load_scene(SCENE)


def _ir(recon=(), responses=()):
    return ResolvedMissionIR(
        tuple(ResolvedReconClause(z) for z in recon),
        tuple(ResolvedResponseClause(i, d) for i, d in responses),
    )


def test_new_graph_recon_plus_full_response(scene):
    ir = _ir(
        recon=[("ZONE_A", "ZONE_C")],
        responses=[(("FIRE_SITE_1",), "GROUND_SUPPRESSION")],
    )
    graph = compile_new_graph(ir, scene)
    keys = {(t.task_type, t.target) for t in graph.tasks}
    assert keys == {
        (TaskType.AREA_RECON, "ZONE_A"),
        (TaskType.AREA_RECON, "ZONE_C"),
        (TaskType.GROUND_INSPECTION, "FIRE_SITE_1"),
        (TaskType.GROUND_SUPPRESSION, "FIRE_SITE_1"),
    }
    assert len(graph.edges) == 1


def test_new_graph_passes_the_validator(scene):
    ir = _ir(
        recon=[("ZONE_A", "ZONE_B", "ZONE_C", "ZONE_D")],
        responses=[
            (("FIRE_SITE_1",), "GROUND_SUPPRESSION"),
            (("FIRE_SITE_2",), "GROUND_INSPECTION"),
        ],
    )
    graph = compile_new_graph(ir, scene)
    cand = MissionCandidate.from_raw({
        "tasks": [{"task_type": t.task_type.value, "target": t.target} for t in graph.tasks],
        "edges": [[f"{graph[p].task_type.value}:{graph[p].target}",
                   f"{graph[s].task_type.value}:{graph[s].target}"] for p, s in graph.edges],
    })[0]
    assert validate_candidate(cand, scene).accepted


def test_dedup_across_clauses(scene):
    ir = _ir(
        recon=[("ZONE_A", "ZONE_B"), ("ZONE_B", "ZONE_C")],
        responses=[
            (("FIRE_SITE_1",), "GROUND_INSPECTION"),
            (("FIRE_SITE_1", "FIRE_SITE_2"), "GROUND_INSPECTION"),
        ],
    )
    graph = compile_new_graph(ir, scene)
    keys = [(t.task_type, t.target) for t in graph.tasks]
    assert len(keys) == len(set(keys))          # no duplicate task
    assert keys.count((TaskType.AREA_RECON, "ZONE_B")) == 1


def test_patch_is_additive_only(scene):
    current = compile_reference_graph(
        scene, [(TaskType.AREA_RECON, "ZONE_A")], [])
    ir = _ir(
        recon=[("ZONE_A", "ZONE_B")],                       # A already there
        responses=[(("FIRE_SITE_1",), "GROUND_SUPPRESSION")],
    )
    patch = compile_patch(ir, current)
    adds = {(o.task_type, o.target) for o in patch.operations if isinstance(o, AddTask)}
    assert adds == {
        (TaskType.AREA_RECON, "ZONE_B"),
        (TaskType.GROUND_INSPECTION, "FIRE_SITE_1"),
        (TaskType.GROUND_SUPPRESSION, "FIRE_SITE_1"),
    }
    assert any(isinstance(o, AddEdge) for o in patch.operations)
    assert not any(type(o).__name__ == "RemoveEdge" for o in patch.operations)


def test_patch_no_change_when_everything_present(scene):
    current = compile_reference_graph(
        scene,
        [(TaskType.AREA_RECON, "ZONE_A"), (TaskType.AREA_RECON, "ZONE_B")],
        [],
    )
    patch = compile_patch(_ir(recon=[("ZONE_A", "ZONE_B")]), current)
    assert patch.operations == []
