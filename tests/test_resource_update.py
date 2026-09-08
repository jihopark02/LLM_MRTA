"""P13.2 safe-checkpoint resource replacement."""

from pathlib import Path

import pytest

from allocation.team import ResourceInfeasibleError, resolve_runtime_team
from core.enums import TaskStatus, TaskType
from execution.executor import SimExecutor, Termination
from interaction.execute import execute_session
from interaction.online_execute import advance_online_session
from interaction.orchestrator import TurnOutcome, handle_turn
from interaction.resources import CountConstraint, ResourceRequest
from interaction.schemas import wire_intent
from interaction.session import MissionSession, fresh_session_state
from llm.backend import MockBackend
from llm.schemas import LLMTask, Step1Output, Step2Output
from scenarios.compiler import compile_reference_graph
from scenarios.scene import load_scene

SCENE = Path(__file__).parents[1] / "scenarios" / "industrial_park.yaml"


@pytest.fixture
def scene():
    return load_scene(SCENE)


def _paused_patrol(scene) -> SimExecutor:
    graph = compile_reference_graph(
        scene,
        [(TaskType.AREA_RECON, zone_id) for zone_id in sorted(scene.zones)],
        [],
    )
    executor = SimExecutor(fresh_session_state(graph, scene), scene)
    advance = executor.advance_to_next_completion()
    assert advance.execution is None
    return executor


def _patrol_outputs(scene):
    return [
        Step1Output(
            tasks=[
                LLMTask(task_type="AREA_RECON", target=zone_id)
                for zone_id in sorted(scene.zones)
            ]
        ),
        Step2Output(edges=[]),
    ]


def _patrol_session(scene) -> MissionSession:
    session = MissionSession("RESOURCE-UPDATE", scene)
    result = handle_turn(
        session,
        "전체 구역을 항공 정찰해줘",
        MockBackend([wire_intent("NEW_MISSION"), *_patrol_outputs(scene)]),
    )
    assert result.outcome is TurnOutcome.COMMITTED
    return session


def _fingerprint(executor: SimExecutor):
    return (
        executor.now,
        executor.active_agent_ids,
        tuple(sorted(executor.assignments.items())),
        tuple(sorted(executor.winning_bids.items())),
        tuple(
            sorted(
                (task.task_id, task.status, task.assigned_agent)
                for task in executor.graph.tasks
            )
        ),
        tuple(
            sorted(
                (
                    aid,
                    agent.position,
                    tuple(agent.bundle),
                    tuple(agent.path),
                    agent.current_task,
                )
                for aid, agent in executor.agents.items()
            )
        ),
        tuple(
            sorted((aid, sim.current, sim.finish_at, sim.busy) for aid, sim in executor.sim.items())
        ),
    )


def test_checkpoint_preserves_active_team_separately_from_full_roster(scene):
    state = _paused_patrol(scene).work
    executor = SimExecutor(state, scene, active_agent_ids=("U1",))

    restored = SimExecutor.from_checkpoint(executor.checkpoint(), scene)

    assert restored.active_agent_ids == ("U1",)
    assert set(restored.agents) == {agent.agent_id for agent in scene.fleet}


def test_runtime_update_excludes_running_agent_only_after_its_commitment(scene):
    executor = _paused_patrol(scene)
    before = _fingerprint(executor)
    running_before = {
        aid: sim.current for aid, sim in executor.sim.items() if sim.current is not None
    }
    assert running_before

    resolved = resolve_runtime_team(
        executor,
        scene,
        ResourceRequest(
            uav=CountConstraint(exact=1),
            ugv=CountConstraint(exact=0),
            excluded_agents=("U2",),
        ),
    )

    assert _fingerprint(executor) == before  # search never mutates the live runtime
    assert len(resolved.active_agents) == 1
    excluded_running = set(running_before) - set(resolved.active_agents)
    assert set(resolved.deferred_exclusions) == excluded_running
    for aid, task_id in running_before.items():
        task = resolved.executor.graph[task_id]
        assert task.status is TaskStatus.RUNNING
        assert task.assigned_agent == aid
        assert resolved.executor.sim[aid].current == task_id

    result = SimExecutor.from_checkpoint(
        resolved.executor.checkpoint(), scene
    ).run()
    assert result.termination is Termination.COMPLETED
    for task_id, aid in result.assignments.items():
        if task_id not in running_before.values():
            assert aid in resolved.active_agents


def test_runtime_infeasibility_is_atomic_and_never_falls_back(scene):
    executor = _paused_patrol(scene)
    before = _fingerprint(executor)

    with pytest.raises(ResourceInfeasibleError):
        resolve_runtime_team(
            executor,
            scene,
            ResourceRequest(
                uav=CountConstraint(exact=0),
                ugv=CountConstraint(exact=0),
            ),
        )

    assert _fingerprint(executor) == before


def test_planning_turn_replaces_policy_and_plan_but_keeps_full_roster(scene):
    session = _patrol_session(scene)

    result = handle_turn(
        session,
        "이제 UAV 한 대만 사용해줘",
        MockBackend(
            [wire_intent("UPDATE_RESOURCES", uav_exact=1, ugv_exact=0)]
        ),
    )

    assert result.outcome is TurnOutcome.COMMITTED
    assert session.active_team == ("U1",)
    assert set(session.state.agents) == {agent.agent_id for agent in scene.fleet}
    assert set(session.plan.assignments.values()) == {"U1"}
    assert session.resource_request.uav.exact == 1
    assert result.audit.resource_resolution.previous_active_team == [
        "G1",
        "G2",
        "U1",
        "U2",
        "U3",
    ]


def test_paused_turn_replaces_team_without_changing_running_commitment(scene):
    session = _patrol_session(scene)
    advance_online_session(session, mode="mock")
    running_before = {
        aid: sim.current
        for aid, sim in session.runtime.sim.items()
        if sim.current is not None
    }
    runtime_before = session.runtime

    result = handle_turn(
        session,
        "이제 UAV 한 대만 사용하고 U2는 제외해줘",
        MockBackend(
            [
                wire_intent(
                    "UPDATE_RESOURCES",
                    uav_exact=1,
                    ugv_exact=0,
                    excluded_agents=["U2"],
                )
            ]
        ),
    )

    assert result.outcome is TurnOutcome.COMMITTED
    assert session.runtime is not runtime_before
    assert session.active_team == ("U1",)
    assert result.audit.resource_resolution.deferred_exclusions == ["U2", "U3"]
    for aid, task_id in running_before.items():
        task = session.runtime.graph[task_id]
        assert task.status is TaskStatus.RUNNING
        assert task.assigned_agent == aid


def test_rejected_paused_resource_turn_preserves_every_live_identity(scene):
    session = _patrol_session(scene)
    advance_online_session(session, mode="mock")
    before = (
        session.runtime,
        session.state,
        session.plan,
        session.resource_request,
        session.active_team,
        session.runtime.now,
        dict(session.runtime.assignments),
    )

    result = handle_turn(
        session,
        "모든 로봇을 제외해줘",
        MockBackend(
            [wire_intent("UPDATE_RESOURCES", uav_exact=0, ugv_exact=0)]
        ),
    )

    assert result.outcome is TurnOutcome.REJECTED
    assert (
        session.runtime,
        session.state,
        session.plan,
        session.resource_request,
        session.active_team,
        session.runtime.now,
        dict(session.runtime.assignments),
    ) == before


def test_one_shot_execution_obeys_selected_team_not_full_roster(scene):
    session = _patrol_session(scene)
    handle_turn(
        session,
        "UAV 한 대만 사용해줘",
        MockBackend(
            [wire_intent("UPDATE_RESOURCES", uav_exact=1, ugv_exact=0)]
        ),
    )

    audit = execute_session(session, mode="mock")

    assert audit.execution_termination == "COMPLETED"
    assert set(audit.execution_assignments.values()) == {"U1"}


def test_report_and_resource_request_commit_as_one_planning_transaction(scene):
    session = _patrol_session(scene)

    result = handle_turn(
        session,
        "Warehouse에 화재가 났어. UGV 한 대로 지상 점검까지 해줘",
        MockBackend(
            [
                wire_intent(
                    "REPORT_INCIDENT",
                    zone_ref="Warehouse",
                    response_up_to="GROUND_INSPECTION",
                    ugv_exact=1,
                )
            ]
        ),
    )

    assert result.outcome is TurnOutcome.COMMITTED
    assert "FIRE_SITE_3" in session.scene.incidents
    assert "GROUND_INSPECTION__FIRE_SITE_3" in session.state.graph
    ugvs = {a for a in session.active_team if a.startswith("G")}
    assert len(ugvs) == 1
    assert "GROUND_INSPECTION__FIRE_SITE_3" in session.plan.assignments


def test_report_and_resource_request_commit_as_one_paused_transaction(scene):
    session = _patrol_session(scene)
    advance_online_session(session, mode="mock")
    running_before = {
        aid: sim.current
        for aid, sim in session.runtime.sim.items()
        if sim.current is not None
    }

    result = handle_turn(
        session,
        "Warehouse에 화재가 났어. UGV 한 대로 지상 점검까지 해줘. G2는 제외해",
        MockBackend(
            [
                wire_intent(
                    "REPORT_INCIDENT",
                    zone_ref="Warehouse",
                    response_up_to="GROUND_INSPECTION",
                    ugv_exact=1,
                    excluded_agents=["G2"],
                )
            ]
        ),
    )

    assert result.outcome is TurnOutcome.COMMITTED
    assert "G1" in session.active_team and "G2" not in session.active_team
    assert "FIRE_SITE_3" in session.scene.incidents
    assert "GROUND_INSPECTION__FIRE_SITE_3" in session.runtime.graph
    for aid, task_id in running_before.items():
        assert session.runtime.sim[aid].current == task_id
        assert session.runtime.graph[task_id].status is TaskStatus.RUNNING
