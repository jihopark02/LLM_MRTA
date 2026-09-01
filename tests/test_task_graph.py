"""Unit tests for TaskGraph (RESEARCH_CONTRACT.md §7, §9, §11). P1 gate items 1, 4."""

import pytest

from core.enums import Capability, PlatformKind, TaskStatus, TaskType
from core.task import Task
from core.task_graph import CycleError, TaskGraph


def task(task_id: str, status: TaskStatus = TaskStatus.PENDING) -> Task:
    return Task(
        task_id=task_id,
        task_type=TaskType.AREA_RECON,
        target="ZONE_A",
        position=(0.0, 0.0),
        priority=1,
        required_capabilities=frozenset({Capability.AERIAL_RECON}),
        eligible_platforms=frozenset({PlatformKind.UAV}),
        duration=10.0,
        status=status,
    )


def chain(*ids: str) -> TaskGraph:
    g = TaskGraph()
    for tid in ids:
        g.add_task(task(tid))
    for a, b in zip(ids, ids[1:], strict=False):
        g.add_edge(a, b)
    return g


def test_add_duplicate_task_id_rejected():
    g = TaskGraph()
    g.add_task(task("T1"))
    with pytest.raises(ValueError):
        g.add_task(task("T1"))


def test_predecessors_and_successors():
    g = chain("A", "B", "C")
    assert g.predecessors("B") == {"A"}
    assert g.successors("B") == {"C"}
    assert g.predecessors("A") == set()
    assert g.edges == {("A", "B"), ("B", "C")}


def test_topological_order_is_deterministic():
    g = chain("A", "B", "C")
    g.add_task(task("X"))
    g.add_edge("A", "X")
    assert g.topological_order() == ["A", "B", "X", "C"]


def test_cycle_detection():
    g = chain("A", "B", "C")
    g.add_edge("C", "A")
    assert g.has_cycle()
    with pytest.raises(CycleError):
        g.topological_order()


def test_reference_errors_flags_unknown_endpoint_and_self_loop():
    g = TaskGraph()
    g.add_task(task("A"))
    g.add_edge("A", "GHOST")
    g.add_edge("A", "A")
    errors = g.reference_errors()
    assert any("unknown task: GHOST" in e for e in errors)
    assert any("self-loop: A" in e for e in errors)


def test_recompute_ready_promotes_only_when_all_predecessors_completed():
    g = chain("A", "B", "C")
    g.recompute_ready()
    assert g.ids_with_status(TaskStatus.READY) == {"A"}
    assert g.ids_with_status(TaskStatus.PENDING) == {"B", "C"}

    g["A"].status = TaskStatus.COMPLETED
    g.recompute_ready()
    assert g.ids_with_status(TaskStatus.READY) == {"B"}
    assert g.ids_with_status(TaskStatus.PENDING) == {"C"}


def test_recompute_ready_leaves_assigned_and_terminal_untouched():
    g = chain("A", "B")
    g["A"].status = TaskStatus.COMPLETED
    g["B"].status = TaskStatus.RUNNING
    g.recompute_ready()
    assert g["B"].status is TaskStatus.RUNNING
