"""P12.1/P12.3: one-turn incident response and atomic candidate publication."""

from pathlib import Path

from allocation.allocate import allocate
from core.enums import TaskType
from interaction.directive import MissionDirective
from interaction.online_execute import advance_online_session
from interaction.orchestrator import TurnOutcome, handle_turn
from interaction.schemas import wire_intent
from interaction.session import MissionSession, fresh_session_state
from llm.backend import MockBackend
from scenarios.fixture import load_reference_fixture
from scenarios.scene import load_scene
from validator.hashing import pre_state_hash, scene_hash

SCENE = Path(__file__).parents[1] / "scenarios" / "industrial_park.yaml"


def _planned(*, policy: str | None = None) -> MissionSession:
    scene = load_scene(SCENE)
    state = fresh_session_state(load_reference_fixture().graph, scene)
    return MissionSession(
        "P12",
        scene,
        state=state,
        plan=allocate(state, scene),
        directive=MissionDirective.from_slot(policy),
    )


def _report(session: MissionSession, **slots):
    return handle_turn(
        session,
        "Warehouse에서 불이 났어",
        MockBackend([wire_intent("REPORT_INCIDENT", zone_ref="Warehouse", **slots)]),
    )


def _target_steps(session: MissionSession, incident_id: str) -> list[str]:
    return sorted(
        task.task_type.value
        for task in session.state.graph.tasks
        if task.target == incident_id
    )


def test_report_uses_session_policy_and_commits_scene_graph_and_plan_together():
    session = _planned(policy="GROUND_SUPPRESSION")

    result = _report(session)

    assert result.outcome is TurnOutcome.COMMITTED
    assert _target_steps(session, "FIRE_SITE_3") == sorted(
        step.value
        for step in (
            TaskType.THERMAL_RECON,
            TaskType.SUPPRESSANT_DROP,
            TaskType.GROUND_INSPECTION,
            TaskType.GROUND_SUPPRESSION,
        )
    )
    assert set(session.plan.assignments) >= {
        task.task_id for task in session.state.graph.tasks if task.target == "FIRE_SITE_3"
    }
    action = result.audit.incident_action
    assert action.source == "OPERATOR"
    assert action.zone_id == "ZONE_A"
    assert action.incident_id == "FIRE_SITE_3"
    assert action.policy_origin == "SESSION_POLICY"
    assert action.response_up_to == "GROUND_SUPPRESSION"
    assert result.patch_result.accepted


def test_explicit_report_step_overrides_session_policy():
    session = _planned(policy="GROUND_SUPPRESSION")

    result = _report(session, response_up_to="SUPPRESSANT_DROP")

    assert result.outcome is TurnOutcome.COMMITTED
    assert _target_steps(session, "FIRE_SITE_3") == [
        "SUPPRESSANT_DROP",
        "THERMAL_RECON",
    ]
    assert result.audit.incident_action.policy_origin == "EXPLICIT"
    assert result.audit.incident_action.response_up_to == "SUPPRESSANT_DROP"


def test_report_without_any_policy_remains_scene_only():
    session = _planned()
    state, plan = session.state, session.plan

    result = _report(session)

    assert result.outcome is TurnOutcome.COMMITTED
    assert session.state is state and session.plan is plan
    assert "FIRE_SITE_3" in session.scene.incidents
    assert result.audit.incident_action.policy_origin == "NONE"
    assert result.audit.incident_action.response_up_to is None
    assert result.patch_result is None


def test_paused_report_and_policy_are_one_online_transaction():
    session = _planned(policy="GROUND_SUPPRESSION")
    advance_online_session(session, mode="mock")
    runtime_before = session.runtime
    signature_before = (
        runtime_before.now,
        pre_state_hash(runtime_before.work),
        scene_hash(runtime_before.scene),
    )

    result = _report(session)

    assert result.outcome is TurnOutcome.COMMITTED
    assert session.runtime is not runtime_before
    assert session.state is session.runtime.work
    assert _target_steps(session, "FIRE_SITE_3") == sorted(
        step.value
        for step in (
            TaskType.THERMAL_RECON,
            TaskType.SUPPRESSANT_DROP,
            TaskType.GROUND_INSPECTION,
            TaskType.GROUND_SUPPRESSION,
        )
    )
    assert result.audit.online_reallocation is not None
    assert result.audit.online_reallocation.policy == "selective"
    assert result.audit.online_reallocation.patch_added_tasks
    assert (
        runtime_before.now,
        pre_state_hash(runtime_before.work),
        scene_hash(runtime_before.scene),
    ) == signature_before


def test_plan_failure_rolls_back_the_new_incident_too(monkeypatch):
    from interaction import orchestrator

    session = _planned(policy="GROUND_SUPPRESSION")
    scene, state, plan = session.scene, session.state, session.plan
    before = (scene_hash(scene), pre_state_hash(state))
    monkeypatch.setattr(
        orchestrator,
        "_plan_for",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("plan failed")),
    )

    result = _report(session)

    assert result.outcome is TurnOutcome.TURN_ERROR
    assert session.scene is scene and session.state is state and session.plan is plan
    assert (scene_hash(session.scene), pre_state_hash(session.state)) == before
    assert "FIRE_SITE_3" not in session.scene.incidents


def test_online_failure_rolls_back_scene_runtime_and_clock(monkeypatch):
    from interaction import orchestrator

    session = _planned(policy="GROUND_SUPPRESSION")
    advance_online_session(session, mode="mock")
    scene, state, runtime = session.scene, session.state, session.runtime
    before = (scene_hash(scene), pre_state_hash(state), runtime.now)
    monkeypatch.setattr(
        orchestrator,
        "apply_online_patch",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("rebid failed")),
    )

    result = _report(session)

    assert result.outcome is TurnOutcome.TURN_ERROR
    assert session.scene is scene and session.state is state and session.runtime is runtime
    assert (scene_hash(session.scene), pre_state_hash(session.state), runtime.now) == before
    assert "FIRE_SITE_3" not in session.scene.incidents


def test_response_request_without_a_mission_clarifies_without_registering():
    scene = load_scene(SCENE)
    session = MissionSession("P12", scene)

    result = _report(session, response_up_to="GROUND_SUPPRESSION")

    assert result.outcome is TurnOutcome.CLARIFICATION
    assert session.scene is scene
    assert "FIRE_SITE_3" not in session.scene.incidents
