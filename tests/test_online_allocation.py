from pathlib import Path

from allocation.online import ReleasePolicy, apply_online_patch
from core.enums import TaskStatus, TaskType
from core.mission_state import MissionState
from execution.executor import SimExecutor, Termination
from interaction.ground import build_chain_patch
from interaction.scene_mut import register_incident
from scenarios.fixture import load_reference_fixture
from scenarios.scene import load_scene
from validator.hashing import graph_hash, pre_state_hash
from validator.patch import AddTask, MissionPatch, graph_edge_keys, graph_hash_nodes
from validator.patch_apply import _assignment_invariant_errors

SCENARIOS = Path(__file__).parents[1] / "scenarios"


def _paused_reference():
    scene = load_scene(SCENARIOS / "industrial_park.yaml")
    graph = load_reference_fixture(SCENARIOS / "reference_fixture.yaml").graph
    state = MissionState(graph, {agent.agent_id: agent for agent in scene.fleet})
    executor = SimExecutor(state, scene)
    advance = executor.advance_to_next_completion()
    assert advance.execution is None
    return executor, scene


def _new_fire_patch(executor, scene):
    updated_scene, incident_id = register_incident(scene, "ZONE_A")
    plan = build_chain_patch(executor.graph, incident_id, "GROUND_SUPPRESSION")
    assert plan.patch is not None
    return updated_scene, plan.patch


def _commitment(executor):
    return {
        task.task_id: (task.status, task.assigned_agent)
        for task in executor.graph.tasks
        if task.status in {TaskStatus.COMPLETED, TaskStatus.RUNNING}
    }


def _checkpoint_signature(checkpoint):
    """Compare checkpoint contents without relying on TaskGraph object identity."""
    work = checkpoint._work
    return (
        graph_hash(graph_hash_nodes(work.graph), sorted(graph_edge_keys(work.graph))),
        pre_state_hash(work),
        checkpoint.now,
        checkpoint.access_nodes,
        checkpoint.sim,
        checkpoint.assignments,
        checkpoint.winning_bids,
        checkpoint.task_departure,
        checkpoint.task_start,
        checkpoint.task_completion,
        checkpoint.consensus_rounds,
        checkpoint.uav_flight,
        checkpoint.ugv_route,
        checkpoint.lam,
        checkpoint.started,
        checkpoint.epoch_pending,
    )


def test_online_patch_is_atomic_and_preserves_completed_and_running_tasks():
    executor, scene = _paused_reference()
    updated_scene, patch = _new_fire_patch(executor, scene)
    original_checkpoint = executor.checkpoint()
    locked = _commitment(executor)

    result = apply_online_patch(executor, patch, updated_scene)

    assert result.accepted
    assert result.executor is not executor
    assert _commitment(result.executor) == locked
    assert _checkpoint_signature(executor.checkpoint()) == _checkpoint_signature(
        original_checkpoint
    )
    assert _assignment_invariant_errors(result.executor.work) == []


def test_selective_policy_releases_affected_uav_suffix_and_not_running_task():
    executor, scene = _paused_reference()
    updated_scene, patch = _new_fire_patch(executor, scene)
    running = {
        task.task_id
        for task in executor.graph.tasks
        if task.status is TaskStatus.RUNNING
    }

    result = apply_online_patch(executor, patch, updated_scene)

    assert result.new_ready_tasks == ("THERMAL_RECON__FIRE_SITE_3",)
    assert result.directly_affected_tasks
    assert result.released_tasks
    assert running.isdisjoint(result.released_tasks)
    assert running <= result.preserved_active_assignments.keys()
    assert "THERMAL_RECON__FIRE_SITE_3" in result.after_assignments


def test_no_reset_full_reset_and_selective_have_distinct_release_contracts():
    executor, scene = _paused_reference()
    updated_scene, patch = _new_fire_patch(executor, scene)

    no_reset = apply_online_patch(
        executor, patch, updated_scene, policy=ReleasePolicy.NO_RESET
    )
    full = apply_online_patch(
        executor, patch, updated_scene, policy=ReleasePolicy.FULL_RESET
    )
    selective = apply_online_patch(
        executor, patch, updated_scene, policy=ReleasePolicy.SELECTIVE
    )

    assert no_reset.released_tasks == ()
    assert set(selective.released_tasks) <= set(full.released_tasks)
    assert set(full.released_tasks) == {
        task.task_id for task in executor.graph.tasks if task.status is TaskStatus.ASSIGNED
    }


def test_rejected_patch_leaves_original_executor_unchanged():
    executor, scene = _paused_reference()
    checkpoint = executor.checkpoint()
    duplicate = MissionPatch([AddTask(TaskType.AREA_RECON, "ZONE_A")])

    result = apply_online_patch(executor, duplicate, scene)

    assert not result.accepted
    assert result.executor is None
    assert _checkpoint_signature(executor.checkpoint()) == _checkpoint_signature(checkpoint)


def test_online_selective_execution_resumes_and_finishes_without_violations():
    executor, scene = _paused_reference()
    updated_scene, patch = _new_fire_patch(executor, scene)
    applied = apply_online_patch(executor, patch, updated_scene)
    resumed = applied.executor
    assert resumed is not None

    result = resumed.run()

    assert result.termination is Termination.COMPLETED
    assert len(result.completed) == 16
    assert result.capability_violations == []
    assert result.precedence_violations == []
    assert _assignment_invariant_errors(resumed.work) == []
