"""P13.1 strict resource requests and deterministic team resolution."""

from pathlib import Path

import pytest

from allocation.allocate import allocate
from allocation.team import ResourceInfeasibleError, resolve_initial_team
from core.enums import TaskType
from interaction.orchestrator import TurnOutcome, handle_turn
from interaction.resources import CountConstraint, ResourceRequest
from interaction.schemas import wire_intent
from interaction.session import MissionSession, fresh_session_state
from llm.backend import MockBackend
from llm.schemas import LLMTask, Step1Output, Step2Output
from scenarios.compiler import compile_reference_graph
from scenarios.fixture import load_reference_fixture
from scenarios.scene import load_scene

SCENE = Path(__file__).parents[1] / "scenarios" / "industrial_park.yaml"


@pytest.fixture
def scene():
    return load_scene(SCENE)


def patrol_state(scene):
    graph = compile_reference_graph(
        scene,
        [(TaskType.AREA_RECON, zone_id) for zone_id in sorted(scene.zones)],
        [],
    )
    return fresh_session_state(graph, scene)


@pytest.mark.parametrize("value", [-1, True, 1.0, "1"])
def test_count_constraint_rejects_laundered_values(value):
    with pytest.raises(ValueError):
        CountConstraint(exact=value)


def test_count_constraint_rejects_conflicting_or_reversed_bounds():
    with pytest.raises(ValueError, match="exact"):
        CountConstraint(exact=1, minimum=1)
    with pytest.raises(ValueError, match="exceed"):
        CountConstraint(minimum=2, maximum=1)


def test_request_rejects_duplicate_and_overlapping_agent_ids():
    with pytest.raises(ValueError, match="duplicate"):
        ResourceRequest(required_agents=("G1", "G1"))
    with pytest.raises(ValueError, match="both"):
        ResourceRequest(required_agents=("G1",), excluded_agents=("G1",))


def test_request_rejects_unknown_agent_at_scene_boundary(scene):
    request = ResourceRequest(required_agents=("NOT_IN_SCENE",))
    with pytest.raises(ValueError, match="unknown agent"):
        request.validate_scene(scene)


def test_unconstrained_resolution_is_exactly_the_existing_full_fleet_path(scene):
    state = patrol_state(scene)
    baseline = allocate(state, scene)
    resolved = resolve_initial_team(state, scene, ResourceRequest())

    assert resolved.active_agents == tuple(sorted(state.agents))
    assert resolved.candidates_tested == 1
    assert resolved.plan.assignments == baseline.assignments
    assert resolved.plan.winning_bids == baseline.winning_bids
    assert resolved.plan.estimated_makespan == baseline.estimated_makespan


def test_one_uav_constraint_changes_the_active_team_and_assignment(scene):
    resolved = resolve_initial_team(
        patrol_state(scene),
        scene,
        ResourceRequest(uav=CountConstraint(exact=1), ugv=CountConstraint(exact=0)),
    )

    assert resolved.active_agents == ("S1",)
    assert set(resolved.plan.assignments.values()) == {"S1"}
    assert len(resolved.plan.assignments) == 4


def test_required_and_excluded_agents_are_enforced_not_ignored():
    fixture = load_reference_fixture()
    state = fresh_session_state(fixture.graph, fixture.scene)
    request = ResourceRequest(required_agents=("G1",), excluded_agents=("G2",))

    resolved = resolve_initial_team(state, fixture.scene, request)

    assert "G1" in resolved.active_agents
    assert "G2" not in resolved.active_agents
    assert "G1" in resolved.plan.assignments.values()
    assert "G2" not in resolved.plan.assignments.values()


def test_infeasible_constraint_never_falls_back_to_full_fleet(scene):
    with pytest.raises(ResourceInfeasibleError, match="no active team"):
        resolve_initial_team(
            patrol_state(scene),
            scene,
            ResourceRequest(uav=CountConstraint(exact=0), ugv=CountConstraint(exact=0)),
        )


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


def test_new_mission_commits_the_resolved_team_and_audits_it(scene):
    session = MissionSession("RESOURCE-ONE", scene)
    backend = MockBackend(
        [
            wire_intent("NEW_MISSION", uav_exact=1, ugv_exact=0),
            *_patrol_outputs(scene),
        ]
    )

    result = handle_turn(session, "UAV 한 대로 전체 구역을 정찰해줘", backend)

    assert result.outcome is TurnOutcome.COMMITTED
    assert session.active_team == ("S1",)
    assert set(session.state.agents) == {agent.agent_id for agent in scene.fleet}
    assert set(session.plan.assignments.values()) == {"S1"}
    audit = result.audit.resource_resolution
    assert audit is not None
    assert audit.active_team == ["S1"]
    assert audit.error_code is None


def test_infeasible_new_mission_is_rejected_atomically(scene):
    session = MissionSession("RESOURCE-NONE", scene)
    backend = MockBackend(
        [
            wire_intent("NEW_MISSION", uav_exact=0, ugv_exact=0),
            *_patrol_outputs(scene),
        ]
    )

    result = handle_turn(session, "로봇 없이 전체 구역을 정찰해줘", backend)

    assert result.outcome is TurnOutcome.REJECTED
    assert session.state is None and session.plan is None
    assert session.active_team == ()
    assert result.audit.resource_resolution.error_code == "RESOURCE_INFEASIBLE"
