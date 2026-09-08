from pathlib import Path

import pytest

from core.enums import TaskStatus
from core.mission_state import MissionState
from execution.executor import SimExecutor, Termination
from scenarios.fixture import load_reference_fixture
from scenarios.scene import load_scene

SCENARIOS = Path(__file__).parents[1] / "scenarios"


def _inputs():
    scene = load_scene(SCENARIOS / "industrial_park.yaml")
    graph = load_reference_fixture(SCENARIOS / "reference_fixture.yaml").graph
    state = MissionState(graph, {agent.agent_id: agent for agent in scene.fleet})
    return state, scene


def _result_signature(result):
    return {
        "termination": result.termination,
        "completed": result.completed,
        "assignments": result.assignments,
        "winning_bids": result.winning_bids,
        "task_departure": result.task_departure,
        "task_start": result.task_start,
        "task_completion": result.task_completion,
        "consensus_rounds": result.consensus_rounds,
        "epochs": result.epochs,
        "makespan": result.makespan,
        "capability_violations": result.capability_violations,
        "precedence_violations": result.precedence_violations,
        "uav_flight_distance": result.uav_flight_distance,
        "ugv_route_distance": result.ugv_route_distance,
        "workload": result.workload,
        "agent_utilization": result.agent_utilization,
        "idle_agents": result.idle_agents,
        "unfinished_tasks": result.unfinished_tasks,
    }


def test_checkpoint_restore_finishes_identically_to_uninterrupted_execution():
    state, scene = _inputs()
    uninterrupted = SimExecutor(state, scene).run()

    paused = SimExecutor(state, scene)
    first = paused.advance_to_next_completion()
    assert first.execution is None
    assert first.completed_now
    restored = SimExecutor.from_checkpoint(first.checkpoint, scene)
    resumed = restored.run()

    assert _result_signature(resumed) == _result_signature(uninterrupted)
    assert resumed.makespan == pytest.approx(149.9, abs=0.1)  # P4 golden (D-060+D-061)


def test_repeated_completion_pauses_equal_uninterrupted_execution():
    state, scene = _inputs()
    expected = SimExecutor(state, scene).run()
    executor = SimExecutor(state, scene)
    events: list[tuple[str, ...]] = []

    while True:
        advance = executor.advance_to_next_completion()
        events.append(advance.completed_now)
        if advance.execution is not None:
            actual = advance.execution
            break
        executor = SimExecutor.from_checkpoint(advance.checkpoint, scene)

    assert all(events)
    assert sum(len(event) for event in events) == 8
    assert _result_signature(actual) == _result_signature(expected)


def test_pause_is_after_completion_and_before_next_ready_epoch():
    state, scene = _inputs()
    executor = SimExecutor(state, scene)

    advance = executor.advance_to_next_completion()

    assert advance.completed_now
    assert executor._epoch_pending
    assert all(
        executor.graph[task_id].status is TaskStatus.COMPLETED
        for task_id in advance.completed_now
    )
    ready = executor.graph.ids_with_status(TaskStatus.READY)
    assert all(task_id not in executor.assignments for task_id in ready)


def test_checkpoint_does_not_share_mutable_state_with_source_or_restore():
    state, scene = _inputs()
    executor = SimExecutor(state, scene)
    first = executor.advance_to_next_completion()
    checkpoint = first.checkpoint
    expected_now = checkpoint.now

    # Advancing the source after capture cannot alter the stored snapshot.
    executor.advance_to_next_completion()
    restored_a = SimExecutor.from_checkpoint(checkpoint, scene)
    assert restored_a.now == expected_now

    # Mutating one restored executor cannot leak into another restore.
    task_id = restored_a.graph.tasks[0].task_id
    restored_a.graph[task_id].status = TaskStatus.CANCELLED
    restored_b = SimExecutor.from_checkpoint(checkpoint, scene)
    assert restored_b.graph[task_id].status is not TaskStatus.CANCELLED


def test_checkpoint_preserves_non_default_scoring_lambda():
    state, scene = _inputs()
    executor = SimExecutor(state, scene, lam=0.97)
    checkpoint = executor.advance_to_next_completion().checkpoint

    restored = SimExecutor.from_checkpoint(checkpoint, scene)

    assert restored.lam == 0.97


def test_terminal_incremental_result_is_completed_and_violation_free():
    state, scene = _inputs()
    executor = SimExecutor(state, scene)
    while True:
        advance = executor.advance_to_next_completion()
        if advance.execution is not None:
            result = advance.execution
            break

    assert result.termination is Termination.COMPLETED
    assert result.capability_violations == []
    assert result.precedence_violations == []
