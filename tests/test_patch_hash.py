"""P8.1b: MissionPatch audit hashes (RESEARCH_CONTRACT.md §14, D-027).

``patch_hash`` identifies the operations; ``pre_state_hash`` identifies the
state they were judged against. Both are needed because the same graph and the
same patch can be accepted, released or rejected with E_RUNNING_LOCKED
depending on the target task's status.
"""

from dataclasses import replace
from pathlib import Path

import pytest

from core.enums import TaskStatus, TaskType
from core.mission_state import MissionState
from scenarios.compiler import compile_reference_graph
from scenarios.scene import load_scene
from validator.errors import ErrorCode
from validator.hashing import VALIDATOR_VERSION, pre_state_hash
from validator.patch import AddEdge, AddTask, MissionPatch, RemoveEdge
from validator.patch_apply import apply_patch

SCENE = Path(__file__).parents[1] / "scenarios" / "industrial_park.yaml"

TR_F1 = (TaskType.THERMAL_RECON, "FIRE_SITE_1")
SD_F1 = (TaskType.SUPPRESSANT_DROP, "FIRE_SITE_1")
GI_F1 = (TaskType.GROUND_INSPECTION, "FIRE_SITE_1")


@pytest.fixture(scope="module")
def scene():
    return load_scene(SCENE)


def state_of(scene, specs, edges=()):
    # Copy the fleet: the scene fixture is module-scoped, and §18.8's warning
    # about sharing mutable Agents applies to tests too.
    graph = compile_reference_graph(scene, list(specs), [tuple(e) for e in edges])
    return MissionState(
        graph, {a.agent_id: replace(a, bundle=[], path=[]) for a in scene.fleet}
    )


def tid(key) -> str:
    return f"{key[0].value}__{key[1]}"


# -- version -----------------------------------------------------------


def test_validator_version_is_1_4():
    assert VALIDATOR_VERSION == "1.4"


# -- patch_hash: identity of the operations ---------------------------


def test_accepted_patch_records_both_hashes(scene):
    st = state_of(scene, [TR_F1])
    _, r = apply_patch(st, MissionPatch([AddTask(*SD_F1), AddEdge(TR_F1, SD_F1)]), scene)
    assert r.accepted
    assert len(r.patch_hash) == 64 and len(r.pre_state_hash) == 64


def test_patch_hash_is_independent_of_operation_order(scene):
    st = state_of(scene, [TR_F1])
    ops = [AddTask(*SD_F1), AddEdge(TR_F1, SD_F1)]
    _, a = apply_patch(st, MissionPatch(list(ops)), scene)
    _, b = apply_patch(st, MissionPatch(list(reversed(ops))), scene)
    assert a.patch_hash == b.patch_hash


def test_different_operations_hash_differently(scene):
    st = state_of(scene, [TR_F1, SD_F1], [(TR_F1, SD_F1)])
    _, a = apply_patch(st, MissionPatch([AddTask(*GI_F1), AddEdge(SD_F1, GI_F1)]), scene)
    _, b = apply_patch(st, MissionPatch([AddTask(TaskType.AREA_RECON, "ZONE_A")]), scene)
    assert a.accepted and b.accepted
    assert a.patch_hash != b.patch_hash


def test_same_patch_on_a_different_base_graph_hashes_differently(scene):
    patch = MissionPatch([AddTask(TaskType.AREA_RECON, "ZONE_A")])
    _, a = apply_patch(state_of(scene, [TR_F1]), patch, scene)
    _, b = apply_patch(state_of(scene, [(TaskType.AREA_RECON, "ZONE_B")]), patch, scene)
    assert a.patch_hash != b.patch_hash


# -- hash recording policy (§14, D-027) -------------------------------


def test_field_schema_failure_has_no_patch_hash(scene):
    # A malformed op has no safe canonical serialization.
    st = state_of(scene, [TR_F1])
    _, r = apply_patch(st, MissionPatch([AddTask("NOT_A_TYPE", "ZONE_A")]), scene)
    assert not r.accepted and ErrorCode.E_SCHEMA in r.error_codes
    assert r.patch_hash is None
    assert len(r.pre_state_hash) == 64  # the state is still recordable


def test_conflict_rejection_records_both_hashes(scene):
    st = state_of(scene, [TR_F1, SD_F1], [(TR_F1, SD_F1)])
    _, r = apply_patch(st, MissionPatch([AddEdge(TR_F1, SD_F1)]), scene)
    assert not r.accepted and ErrorCode.E_PATCH_CONFLICT in r.error_codes
    assert len(r.patch_hash) == 64 and len(r.pre_state_hash) == 64


def test_whole_graph_rejection_records_both_hashes(scene):
    st = state_of(scene, [TR_F1, SD_F1], [(TR_F1, SD_F1)])
    _, r = apply_patch(st, MissionPatch([RemoveEdge(TR_F1, SD_F1)]), scene)
    assert not r.accepted and ErrorCode.E_WORKFLOW in r.error_codes
    assert len(r.patch_hash) == 64 and len(r.pre_state_hash) == 64


# -- pre_state_hash: the verdict depends on task status ---------------


def test_same_graph_and_patch_but_different_status_hash_differently(scene):
    a = state_of(scene, [TR_F1, SD_F1], [(TR_F1, SD_F1)])
    b = state_of(scene, [TR_F1, SD_F1], [(TR_F1, SD_F1)])
    b.graph[tid(SD_F1)].status = TaskStatus.COMPLETED

    patch = MissionPatch([AddTask(*GI_F1), AddEdge(SD_F1, GI_F1)])
    _, ra = apply_patch(a, patch, scene)
    _, rb = apply_patch(b, patch, scene)

    assert ra.patch_hash == rb.patch_hash          # same operations
    assert ra.pre_state_hash != rb.pre_state_hash  # different state


def test_pre_state_hash_preserves_bundle_and_path_order(scene):
    # [A, B] and [B, A] are different CBBA execution orders and must not collide.
    a = state_of(scene, [TR_F1, SD_F1], [(TR_F1, SD_F1)])
    a.agents["R1"].path = [tid(TR_F1), tid(SD_F1)]
    b = state_of(scene, [TR_F1, SD_F1], [(TR_F1, SD_F1)])
    b.agents["R1"].path = [tid(SD_F1), tid(TR_F1)]
    assert pre_state_hash(a) != pre_state_hash(b)

    a.agents["R1"].bundle = [tid(TR_F1), tid(SD_F1)]
    b.agents["R1"].bundle = [tid(SD_F1), tid(TR_F1)]
    b.agents["R1"].path = [tid(TR_F1), tid(SD_F1)]
    assert pre_state_hash(a) != pre_state_hash(b)


def test_pre_state_hash_separates_the_agent_key_from_the_agent_id(scene):
    # §10 rule 6 rejects a state whose agents dict key disagrees with the
    # Agent's own id. Hashing only the key would give that rejected state the
    # same audit hash as the accepted one (§14).
    ok = state_of(scene, [TR_F1])
    broken = state_of(scene, [TR_F1])
    broken.agents["G1"] = replace(broken.agents["G1"], agent_id="BROKEN")

    patch = MissionPatch([AddTask(*SD_F1), AddEdge(TR_F1, SD_F1)])
    _, ra = apply_patch(ok, patch, scene)
    _, rb = apply_patch(broken, patch, scene)

    assert ra.accepted
    assert not rb.accepted and ErrorCode.E_SCHEMA in rb.error_codes
    assert ra.patch_hash == rb.patch_hash            # same operations
    assert ra.pre_state_hash != rb.pre_state_hash    # different state, different verdict


def test_pre_state_hash_ignores_agent_dict_order(scene):
    a = state_of(scene, [TR_F1])
    b = state_of(scene, [TR_F1])
    b.agents = dict(reversed(list(b.agents.items())))
    assert pre_state_hash(a) == pre_state_hash(b)


def test_pre_state_hash_tracks_assignment_and_bids(scene):
    base = state_of(scene, [TR_F1])
    before = pre_state_hash(base)

    base.graph[tid(TR_F1)].status = TaskStatus.ASSIGNED
    base.graph[tid(TR_F1)].assigned_agent = "S1"
    assert pre_state_hash(base) != before

    with_bid = pre_state_hash(base)
    base.winning_bids[tid(TR_F1)] = 3.5
    assert pre_state_hash(base) != with_bid


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_bid_is_not_auditable(scene, bad):
    st = state_of(scene, [TR_F1])
    st.winning_bids[tid(TR_F1)] = bad
    with pytest.raises(ValueError, match="finite"):
        pre_state_hash(st)


def test_float_bids_round_trip_losslessly(scene):
    # float.hex() keeps bids that differ below repr precision distinguishable.
    a = state_of(scene, [TR_F1])
    b = state_of(scene, [TR_F1])
    a.winning_bids[tid(TR_F1)] = 0.1 + 0.2
    b.winning_bids[tid(TR_F1)] = 0.3
    assert pre_state_hash(a) != pre_state_hash(b)


# -- AddTask priority is derived, not carried (§10, D-027) ------------


def test_add_task_priority_is_derived_from_the_scene(scene):
    st = state_of(scene, [TR_F1, SD_F1, GI_F1], [(TR_F1, SD_F1), (SD_F1, GI_F1)])
    new, r = apply_patch(
        st,
        MissionPatch(
            [
                AddTask(TaskType.GROUND_SUPPRESSION, "FIRE_SITE_1"),
                AddEdge(GI_F1, (TaskType.GROUND_SUPPRESSION, "FIRE_SITE_1")),
                AddTask(TaskType.AREA_RECON, "ZONE_A"),
            ]
        ),
        scene,
    )
    assert r.accepted, r.rejection_errors
    assert new.graph["GROUND_SUPPRESSION__FIRE_SITE_1"].priority == 9  # FIRE_SITE_1
    assert new.graph["AREA_RECON__ZONE_A"].priority == 4               # AREA_RECON_PRIORITY


def test_add_task_on_the_lower_priority_incident_derives_7(scene):
    tr2 = (TaskType.THERMAL_RECON, "FIRE_SITE_2")
    st = state_of(scene, [tr2])
    new, r = apply_patch(
        st,
        MissionPatch(
            [
                AddTask(TaskType.SUPPRESSANT_DROP, "FIRE_SITE_2"),
                AddEdge(tr2, (TaskType.SUPPRESSANT_DROP, "FIRE_SITE_2")),
            ]
        ),
        scene,
    )
    assert r.accepted, r.rejection_errors
    assert new.graph["SUPPRESSANT_DROP__FIRE_SITE_2"].priority == 7


def test_add_task_to_an_operator_style_zone_incident_uses_the_response_point(scene):
    # A scene-registered incident placed at ZONE_C's response point compiles
    # its UGV task to that zone's route node (§18.10 uses the same fields).
    from core.enums import IncidentStatus
    from scenarios.scene import Incident

    zone = scene.zones["ZONE_C"]
    extended = replace(
        scene,
        incidents={
            **scene.incidents,
            "FIRE_SITE_3": Incident(
                incident_id="FIRE_SITE_3",
                zone="ZONE_C",
                priority=7,
                position=zone.reported_incident_position,
                access_node=zone.reported_incident_access_node,
                status=IncidentStatus.RESPONSE_REQUIRED,
            ),
        },
    )
    tr3 = (TaskType.THERMAL_RECON, "FIRE_SITE_3")
    st = state_of(extended, [tr3])
    new, r = apply_patch(
        st,
        MissionPatch(
            [
                AddTask(TaskType.SUPPRESSANT_DROP, "FIRE_SITE_3"),
                AddEdge(tr3, (TaskType.SUPPRESSANT_DROP, "FIRE_SITE_3")),
            ]
        ),
        extended,
    )
    assert r.accepted, r.rejection_errors
    assert new.graph["SUPPRESSANT_DROP__FIRE_SITE_3"].priority == 7
    assert new.graph["THERMAL_RECON__FIRE_SITE_3"].position == zone.reported_incident_position


# -- operation dispatch is by type, not by class name -----------------


def test_canonical_op_handles_a_subclassed_operation(scene):
    # A subclass passes the isinstance-based field-schema check, so hashing
    # must not dispatch on type(op).__name__.
    class TaggedAddTask(AddTask):
        pass

    st = state_of(scene, [TR_F1])
    patch = MissionPatch([TaggedAddTask(*SD_F1), AddEdge(TR_F1, SD_F1)])
    _, r = apply_patch(st, patch, scene)
    assert r.accepted, r.rejection_errors
    assert len(r.patch_hash) == 64

    _, plain = apply_patch(st, MissionPatch([AddTask(*SD_F1), AddEdge(TR_F1, SD_F1)]), scene)
    assert r.patch_hash == plain.patch_hash  # same operation, same identity


def test_canonical_op_rejects_a_non_operation():
    from validator.hashing import patch_hash as _ph

    with pytest.raises(ValueError, match="not a MissionPatch operation"):
        _ph("g", "s", ["not an op"], "1.4")
