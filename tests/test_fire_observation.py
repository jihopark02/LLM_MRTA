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


def test_approving_a_held_fire_runs_the_incident_transaction():
    from interaction.observe import ApprovalDecision, enqueue_fire_approvals, resolve_fire_approval

    session = _session(policy=None)  # no session policy: the operator's scope decides
    enqueue_fire_approvals(session, (_observation(session, zone_id="ZONE_B"),), mode="mock")

    audit = resolve_fire_approval(
        session,
        decision=ApprovalDecision.APPROVE,
        response_up_to=TaskType.GROUND_SUPPRESSION,
        mode="mock",
    )

    assert audit.outcome == "COMMITTED"
    assert audit.policy_origin == "EXPLICIT"
    assert audit.response_up_to == "GROUND_SUPPRESSION"
    assert session.pending_approvals == ()
    assert "FIRE_SITE_1" in session.scene.incidents
    targets = {task.target for task in session.state.graph.tasks}
    assert "FIRE_SITE_1" in targets


def test_declining_a_held_fire_changes_nothing():
    from interaction.observe import ApprovalDecision, enqueue_fire_approvals, resolve_fire_approval

    session = _session()
    before = scene_hash(session.scene), _graph_shape(session)
    enqueue_fire_approvals(session, (_observation(session, zone_id="ZONE_B"),), mode="mock")

    audit = resolve_fire_approval(session, decision=ApprovalDecision.DECLINE, mode="mock")

    assert audit.outcome == "DECLINED"
    assert session.pending_approvals == ()
    assert (scene_hash(session.scene), _graph_shape(session)) == before
    assert "FIRE_SITE_1" not in session.scene.incidents


def test_two_fires_are_resolved_in_queue_order():
    from interaction.observe import ApprovalDecision, enqueue_fire_approvals, resolve_fire_approval

    session = _session(policy=None)
    obs = (
        _observation(session, zone_id="ZONE_A"),
        _observation(session, zone_id="ZONE_C"),
    )
    enqueue_fire_approvals(session, obs, mode="mock")
    assert [p.zone_id for p in session.pending_approvals] == ["ZONE_A", "ZONE_C"]

    first = resolve_fire_approval(
        session, decision=ApprovalDecision.DECLINE, mode="mock"
    )
    assert first.zone_id == "ZONE_A"
    assert [p.zone_id for p in session.pending_approvals] == ["ZONE_C"]

    second = resolve_fire_approval(
        session,
        decision=ApprovalDecision.APPROVE,
        response_up_to=TaskType.GROUND_INSPECTION,
        mode="mock",
    )
    assert second.zone_id == "ZONE_C"
    assert session.pending_approvals == ()


def test_approving_without_a_scope_is_rejected():
    import pytest

    from interaction.observe import ApprovalDecision, enqueue_fire_approvals, resolve_fire_approval

    session = _session()
    enqueue_fire_approvals(session, (_observation(session, zone_id="ZONE_B"),), mode="mock")
    with pytest.raises(ValueError, match="workflow scope"):
        resolve_fire_approval(session, decision=ApprovalDecision.APPROVE, mode="mock")
    with pytest.raises(ValueError, match="no fire approval is pending"):
        resolve_fire_approval(
            _session(), decision=ApprovalDecision.DECLINE, mode="mock"
        )
