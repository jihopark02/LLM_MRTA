"""P12.3: sensor/operator convergence on one atomic incident transaction."""

from pathlib import Path

from allocation.allocate import allocate
from core.enums import TaskType
from interaction.directive import MissionDirective
from interaction.observe import apply_fire_observation
from interaction.online_execute import advance_online_session
from interaction.orchestrator import TurnOutcome, handle_turn
from interaction.schemas import wire_intent
from interaction.session import MissionSession, fresh_session_state
from llm.backend import MockBackend
from scenarios.compiler import compile_reference_graph
from scenarios.latent import FireDetectedObservation
from scenarios.scene import load_scene
from validator.hashing import pre_state_hash, scene_hash
from validator.patch import graph_edge_keys, graph_hash_nodes

SCENE = Path(__file__).parents[1] / "scenarios" / "patrol_park.yaml"


def _session(*, policy: str | None = "GROUND_SUPPRESSION") -> MissionSession:
    scene = load_scene(SCENE)
    graph = compile_reference_graph(
        scene,
        [(TaskType.AREA_RECON, zone_id) for zone_id in sorted(scene.zones)],
        [],
    )
    state = fresh_session_state(graph, scene)
    return MissionSession(
        "OBS",
        scene,
        state=state,
        plan=allocate(state, scene),
        directive=MissionDirective.from_slot(policy),
    )


def _observation(session: MissionSession, *, zone_id: str = "ZONE_B"):
    trigger = f"AREA_RECON__{zone_id}"
    owner = session.plan.assignments[trigger]
    now = session.runtime.now if session.runtime is not None else 0.0
    return FireDetectedObservation("latent-f1", zone_id, trigger, owner, now)


def _graph_shape(session: MissionSession):
    return graph_hash_nodes(session.state.graph), graph_edge_keys(session.state.graph)


def test_sensor_and_operator_create_the_same_scene_and_graph_diff():
    operator = _session()
    sensor = _session()

    turn = handle_turn(
        operator,
        "Processing Area에서 불이 났어. 지상 진압까지 대응해줘",
        MockBackend(
            [
                wire_intent(
                    "REPORT_INCIDENT",
                    zone_ref="Processing Area",
                    response_up_to="GROUND_SUPPRESSION",
                )
            ]
        ),
    )
    event = apply_fire_observation(sensor, _observation(sensor), mode="mock")

    assert turn.outcome is TurnOutcome.COMMITTED
    assert event.outcome == "COMMITTED"
    assert scene_hash(operator.scene) == scene_hash(sensor.scene)
    assert _graph_shape(operator) == _graph_shape(sensor)
    assert turn.patch_result.added_tasks == tuple(event.patch.added_tasks)
    assert turn.audit.incident_action.source == "OPERATOR"
    assert event.source == "SENSOR_SIMULATED"
    assert event.policy_origin == "SESSION_POLICY"
    assert event.response_up_to == "GROUND_SUPPRESSION"


def test_sensor_without_policy_registers_incident_but_does_not_invent_tasks():
    session = _session(policy=None)
    state, plan = session.state, session.plan

    event = apply_fire_observation(session, _observation(session), mode="mock")

    assert event.outcome == "COMMITTED"
    assert event.policy_origin == "NONE"
    assert event.response_up_to is None
    assert event.patch is None
    assert session.state is state and session.plan is plan
    assert set(session.scene.incidents) == {"FIRE_SITE_1"}


def test_paused_sensor_event_uses_selective_online_reallocation():
    session = _session()
    advance_online_session(session, mode="mock")
    old_runtime = session.runtime
    old_signature = old_runtime.now, pre_state_hash(old_runtime.work)

    event = apply_fire_observation(session, _observation(session), mode="mock")

    assert event.outcome == "COMMITTED"
    assert event.online_reallocation is not None
    assert event.online_reallocation.policy == "selective"
    assert event.online_reallocation.patch_added_tasks
    assert session.runtime is not old_runtime
    assert session.state is session.runtime.work
    assert (old_runtime.now, pre_state_hash(old_runtime.work)) == old_signature


def test_sensor_planner_failure_preserves_all_mission_objects_and_hashes():
    session = _session()
    scene, state, plan = session.scene, session.state, session.plan
    before = scene_hash(scene), pre_state_hash(state)

    event = apply_fire_observation(
        session,
        _observation(session),
        mode="mock",
        planner=lambda *args: (_ for _ in ()).throw(RuntimeError("planner failed")),
    )

    assert event.outcome == "TURN_ERROR"
    assert event.error_type == "RuntimeError"
    assert session.scene is scene and session.state is state and session.plan is plan
    assert (scene_hash(session.scene), pre_state_hash(session.state)) == before
    assert "FIRE_SITE_1" not in session.scene.incidents


def test_sensor_online_failure_preserves_runtime_time_and_completed_prefix():
    session = _session()
    advance_online_session(session, mode="mock")
    scene, state, runtime = session.scene, session.state, session.runtime
    checkpoint = runtime.checkpoint()

    event = apply_fire_observation(
        session,
        _observation(session),
        mode="mock",
        online_applier=lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("rebid failed")
        ),
    )

    assert event.outcome == "TURN_ERROR"
    assert session.scene is scene and session.state is state and session.runtime is runtime
    after = runtime.checkpoint()
    assert after.now == checkpoint.now
    assert {
        task.task_id for task in after._work.graph.tasks if task.status.value == "COMPLETED"
    } == {
        task.task_id
        for task in checkpoint._work.graph.tasks
        if task.status.value == "COMPLETED"
    }
    assert pre_state_hash(after._work) == pre_state_hash(checkpoint._work)
    assert "FIRE_SITE_1" not in session.scene.incidents


def test_sensor_event_is_typed_and_serialises_in_chronological_stream():
    from interaction.audit_io import session_audit_payload

    session = _session()
    advance_online_session(session, mode="mock")
    event = apply_fire_observation(session, _observation(session), mode="mock")

    payload = session_audit_payload(session)
    assert [item["event_type"] for item in payload["events"]] == [
        "EXECUTION_CHECKPOINT",
        "INCIDENT_OBSERVATION",
    ]
    assert payload["events"][1]["event_seq"] == 1
    assert payload["events"][1]["fixture_id"] == event.fixture_id
    assert payload["events"][1]["patch_hash"] == event.patch_hash


# -- §22.8 sensor fire-detection approval gate (D-065) ------------------------

def test_enqueue_fire_approval_holds_the_fire_without_touching_scene_or_graph():
    from interaction.observe import enqueue_fire_approvals

    session = _session()
    before = scene_hash(session.scene), _graph_shape(session)
    obs = _observation(session, zone_id="ZONE_B")

    audits = enqueue_fire_approvals(session, (obs,), mode="mock")

    assert len(audits) == 1 and audits[0].outcome == "AWAITING_APPROVAL"
    assert len(session.pending_approvals) == 1
    assert session.pending_approvals[0].zone_id == "ZONE_B"
    assert (scene_hash(session.scene), _graph_shape(session)) == before
    assert "FIRE_SITE_1" not in session.scene.incidents


def test_a_recorded_decision_is_not_applied_until_the_boundary():
    from interaction.observe import (
        ApprovalDecision,
        apply_recorded_fire_decisions,
        enqueue_fire_approvals,
        record_fire_decision,
    )

    session = _session(policy=None)
    before = scene_hash(session.scene), _graph_shape(session)
    enqueue_fire_approvals(session, (_observation(session, zone_id="ZONE_B"),), mode="mock")

    recorded = record_fire_decision(
        session,
        decision=ApprovalDecision.APPROVE,
        response_up_to=TaskType.GROUND_SUPPRESSION,
    )
    assert recorded.decided and recorded.approved_scope is TaskType.GROUND_SUPPRESSION
    # still queued, nothing applied yet
    assert len(session.pending_approvals) == 1
    assert (scene_hash(session.scene), _graph_shape(session)) == before

    audits = apply_recorded_fire_decisions(session, mode="mock")

    assert [a.outcome for a in audits] == ["COMMITTED"]
    assert audits[0].policy_origin == "EXPLICIT"
    assert session.pending_approvals == ()
    assert "FIRE_SITE_1" in session.scene.incidents


def test_declining_a_held_fire_changes_nothing():
    from interaction.observe import (
        ApprovalDecision,
        apply_recorded_fire_decisions,
        enqueue_fire_approvals,
        record_fire_decision,
    )

    session = _session()
    before = scene_hash(session.scene), _graph_shape(session)
    enqueue_fire_approvals(session, (_observation(session, zone_id="ZONE_B"),), mode="mock")

    record_fire_decision(session, decision=ApprovalDecision.DECLINE)
    audits = apply_recorded_fire_decisions(session, mode="mock")

    assert [a.outcome for a in audits] == ["DECLINED"]
    assert session.pending_approvals == ()
    assert (scene_hash(session.scene), _graph_shape(session)) == before
    assert "FIRE_SITE_1" not in session.scene.incidents


def test_apply_stops_at_the_first_undecided_fire_preserving_order():
    from interaction.observe import (
        ApprovalDecision,
        apply_recorded_fire_decisions,
        enqueue_fire_approvals,
        has_undecided_fire,
        record_fire_decision,
    )

    session = _session(policy=None)
    obs = (
        _observation(session, zone_id="ZONE_A"),
        _observation(session, zone_id="ZONE_C"),
    )
    enqueue_fire_approvals(session, obs, mode="mock")
    assert [p.zone_id for p in session.pending_approvals] == ["ZONE_A", "ZONE_C"]

    # decide only the second one: the FIFO head is still undecided
    record_fire_decision(session, decision=ApprovalDecision.DECLINE)  # decides ZONE_A
    record_fire_decision(
        session, decision=ApprovalDecision.APPROVE, response_up_to=TaskType.GROUND_INSPECTION
    )  # decides ZONE_C

    audits = apply_recorded_fire_decisions(session, mode="mock")
    assert [a.zone_id for a in audits] == ["ZONE_A", "ZONE_C"]
    assert not has_undecided_fire(session)


def test_apply_leaves_an_undecided_head_in_place():
    from interaction.observe import (
        apply_recorded_fire_decisions,
        enqueue_fire_approvals,
        has_undecided_fire,
    )

    session = _session(policy=None)
    enqueue_fire_approvals(session, (_observation(session, zone_id="ZONE_A"),), mode="mock")

    audits = apply_recorded_fire_decisions(session, mode="mock")
    assert audits == ()
    assert has_undecided_fire(session)
    assert len(session.pending_approvals) == 1


def test_recording_without_a_scope_or_a_pending_fire_is_rejected():
    import pytest

    from interaction.observe import (
        ApprovalDecision,
        enqueue_fire_approvals,
        record_fire_decision,
    )

    session = _session()
    enqueue_fire_approvals(session, (_observation(session, zone_id="ZONE_B"),), mode="mock")
    with pytest.raises(ValueError, match="workflow scope"):
        record_fire_decision(session, decision=ApprovalDecision.APPROVE)
    record_fire_decision(session, decision=ApprovalDecision.DECLINE)
    with pytest.raises(ValueError, match="no undecided fire approval"):
        record_fire_decision(session, decision=ApprovalDecision.DECLINE)
