"""MissionPatch application + reconciliation + multi-transaction (§9 note, §10)."""

from pathlib import Path

import pytest

from core.enums import TaskStatus, TaskType
from core.mission_state import MissionState
from scenarios.compiler import compile_reference_graph
from scenarios.scene import load_scene
from validator.errors import ErrorCode
from validator.patch import AddEdge, AddTask, MissionPatch, RemoveEdge
from validator.patch_apply import _predecessor_diff, _reconcile, apply_patch

SCEN = Path(__file__).parents[1] / "scenarios"

AR_A = (TaskType.AREA_RECON, "ZONE_A")
AR_B = (TaskType.AREA_RECON, "ZONE_B")
TR_F1 = (TaskType.THERMAL_RECON, "FIRE_SITE_1")
SD_F1 = (TaskType.SUPPRESSANT_DROP, "FIRE_SITE_1")
GI_F1 = (TaskType.GROUND_INSPECTION, "FIRE_SITE_1")
HM_F1 = (TaskType.GROUND_SUPPRESSION, "FIRE_SITE_1")


def tid(key):
    return f"{key[0].value}__{key[1]}"


@pytest.fixture
def scene():
    return load_scene(SCEN / "industrial_park.yaml")


def mini_state(scene, specs, edges=()):
    graph = compile_reference_graph(
        scene, [(tt, tgt, 5) for tt, tgt in specs], [tuple(e) for e in edges]
    )
    return MissionState(graph=graph, agents={a.agent_id: a for a in scene.fleet})


# -- apply_patch: op conflicts / transaction ------------------------------


def test_conflicting_patch_rejected_state_untouched(scene):
    state = mini_state(scene, [TR_F1, SD_F1], [(TR_F1, SD_F1)])
    new_state, result = apply_patch(state, MissionPatch([AddEdge(TR_F1, SD_F1)]), scene)
    assert not result.accepted
    assert result.error_codes == [ErrorCode.E_PATCH_CONFLICT]
    assert new_state is state


def test_unknown_add_task_target_is_flagged(scene):
    state = mini_state(scene, [AR_A])
    _, result = apply_patch(
        state, MissionPatch([AddTask(TaskType.AREA_RECON, "ZONE_Z", 3)]), scene
    )
    assert not result.accepted
    assert ErrorCode.E_UNKNOWN_REF in result.error_codes


# -- apply_patch: whole-graph re-validation, incl. multi-transaction ------


def test_single_patch_cycle_rejected(scene):
    state = mini_state(scene, [TR_F1, SD_F1, GI_F1], [(TR_F1, SD_F1), (SD_F1, GI_F1)])
    _, result = apply_patch(state, MissionPatch([AddEdge(GI_F1, TR_F1)]), scene)
    assert ErrorCode.E_CYCLE in result.error_codes


def test_multi_transaction_bypass_is_blocked(scene):
    state = mini_state(scene, [TR_F1, SD_F1], [(TR_F1, SD_F1)])

    s1, r1 = apply_patch(
        state,
        MissionPatch([AddTask(*GI_F1, 5), AddEdge(SD_F1, GI_F1)]),
        scene,
    )
    assert r1.accepted, r1.rejection_errors
    assert len(s1.graph) == 3

    # Isolated, p2 is "one new edge". Against the FULL graph it closes a cycle.
    s2, r2 = apply_patch(s1, MissionPatch([AddEdge(GI_F1, TR_F1)]), scene)
    assert not r2.accepted
    assert ErrorCode.E_CYCLE in r2.error_codes
    assert s2 is s1


def test_sequential_valid_patches_accumulate(scene):
    state = mini_state(scene, [TR_F1], [])
    s1, r1 = apply_patch(
        state, MissionPatch([AddTask(*SD_F1, 5), AddEdge(TR_F1, SD_F1)]), scene
    )
    s2, r2 = apply_patch(
        s1, MissionPatch([AddTask(*GI_F1, 5), AddEdge(SD_F1, GI_F1)]), scene
    )
    assert r1.accepted and r2.accepted
    assert len(s2.graph) == 3
    assert len(state.graph) == 1  # original never mutated
    assert r2.added_tasks == ("GROUND_INSPECTION__FIRE_SITE_1",)
    assert len(r2.graph_hash) == 64 and r2.validator_version == "1.2"


def test_orphaning_a_workflow_task_is_rejected(scene):
    state = mini_state(scene, [TR_F1, SD_F1], [(TR_F1, SD_F1)])
    _, result = apply_patch(state, MissionPatch([RemoveEdge(TR_F1, SD_F1)]), scene)
    assert ErrorCode.E_WORKFLOW in result.error_codes


# -- #13 terminal immutability ------------------------------------------


def test_terminal_incoming_edge_change_is_rejected(scene):
    state = mini_state(scene, [TR_F1, SD_F1], [(TR_F1, SD_F1)])
    state.graph[tid(SD_F1)].status = TaskStatus.COMPLETED
    # Try to add GROUND_INSPECTION and wire it *into* the completed SD (incoming).
    patch = MissionPatch([AddTask(*GI_F1, 5), AddEdge(GI_F1, SD_F1)])
    _, result = apply_patch(state, patch, scene)
    assert not result.accepted
    assert ErrorCode.E_TERMINAL_IMMUTABLE in result.error_codes


def test_13_does_not_block_outgoing_change_by_itself(scene):
    # Removing a terminal task's *outgoing* edge is not E_TERMINAL_IMMUTABLE
    # (it is rejected by #10 instead, because GI would be orphaned).
    state = mini_state(scene, [TR_F1, SD_F1, GI_F1], [(TR_F1, SD_F1), (SD_F1, GI_F1)])
    state.graph[tid(SD_F1)].status = TaskStatus.COMPLETED
    _, result = apply_patch(state, MissionPatch([RemoveEdge(SD_F1, GI_F1)]), scene)
    assert not result.accepted
    assert ErrorCode.E_TERMINAL_IMMUTABLE not in result.error_codes
    assert ErrorCode.E_WORKFLOW in result.error_codes


# -- reconciliation unit tests (release path, unreachable end-to-end in P2) --


def test_predecessor_diff_detects_added_and_removed(scene):
    base = compile_reference_graph(scene, [(*TR_F1, 5), (*SD_F1, 5)], [(TR_F1, SD_F1)])
    final = base.clone()
    final.remove_edge(tid(TR_F1), tid(SD_F1))
    assert _predecessor_diff(base, final) == {tid(SD_F1)}


def test_reconcile_releases_assigned_task(scene):
    graph = compile_reference_graph(scene, [(*TR_F1, 5), (*SD_F1, 5)], [(TR_F1, SD_F1)])
    state = MissionState(graph, {a.agent_id: a for a in scene.fleet})
    sd = state.graph[tid(SD_F1)]
    sd.status = TaskStatus.ASSIGNED
    sd.assigned_agent = "R1"
    state.agents["R1"].bundle.append(tid(SD_F1))
    state.winning_bids[tid(SD_F1)] = 3.0

    work = state.clone()
    work.graph.remove_edge(tid(TR_F1), tid(SD_F1))
    released, changes, errors = _reconcile(work, state.graph, {tid(SD_F1)})

    assert errors == []
    assert released == [tid(SD_F1)]
    assert work.graph[tid(SD_F1)].assigned_agent is None
    assert tid(SD_F1) not in work.agents["R1"].bundle
    assert tid(SD_F1) not in work.winning_bids
    assert (tid(SD_F1), "ASSIGNED", "PENDING") in changes
    # original state untouched
    assert state.graph[tid(SD_F1)].status is TaskStatus.ASSIGNED


def test_empty_patch_rejected_when_state_assignment_is_inconsistent(scene):
    state = mini_state(scene, [TR_F1, SD_F1], [(TR_F1, SD_F1)])
    sd = state.graph[tid(SD_F1)]
    sd.status = TaskStatus.ASSIGNED
    sd.assigned_agent = "MISSING_AGENT"  # not in the fleet, no bundle entry
    _, result = apply_patch(state, MissionPatch([]), scene)
    assert not result.accepted
    assert ErrorCode.E_SCHEMA in result.error_codes


def test_assignment_invariant_flags_multi_owner_and_stale_bid(scene):
    from validator.patch_apply import _assignment_invariant_errors

    state = mini_state(scene, [TR_F1, SD_F1], [(TR_F1, SD_F1)])
    state.graph[tid(SD_F1)].status = TaskStatus.ASSIGNED
    state.graph[tid(SD_F1)].assigned_agent = "R1"
    state.agents["R1"].bundle.append(tid(SD_F1))
    state.agents["R2"].bundle.append(tid(SD_F1))  # second owner
    state.winning_bids[tid(TR_F1)] = 1.0  # TR is READY, not active -> stale
    errs = _assignment_invariant_errors(state)
    details = " ".join(e.detail for e in errs)
    assert "multiple agents" in details
    assert "stale winning_bid" in details


def test_assignment_invariant_flags_dangling_references(scene):
    from validator.patch_apply import _assignment_invariant_errors

    state = mini_state(scene, [TR_F1], [])
    state.agents["S1"].bundle.append("GHOST_TASK")
    state.winning_bids["ALSO_GHOST"] = 3.0
    details = " ".join(e.detail for e in _assignment_invariant_errors(state))
    assert "unknown task 'GHOST_TASK'" in details
    assert "winning_bids references unknown task" in details


def test_dangling_bundle_reference_rejects_empty_patch(scene):
    state = mini_state(scene, [TR_F1], [])
    state.agents["S1"].bundle.append("GHOST_TASK")
    _, result = apply_patch(state, MissionPatch([]), scene)
    assert not result.accepted
    assert ErrorCode.E_SCHEMA in result.error_codes


def test_reconcile_running_predecessor_change_is_fatal(scene):
    graph = compile_reference_graph(scene, [(*TR_F1, 5), (*SD_F1, 5)], [(TR_F1, SD_F1)])
    state = MissionState(graph, {a.agent_id: a for a in scene.fleet})
    state.graph[tid(SD_F1)].status = TaskStatus.RUNNING

    work = state.clone()
    work.graph.remove_edge(tid(TR_F1), tid(SD_F1))
    _, _, errors = _reconcile(work, state.graph, {tid(SD_F1)})
    assert [e.code for e in errors] == [ErrorCode.E_RUNNING_LOCKED]
