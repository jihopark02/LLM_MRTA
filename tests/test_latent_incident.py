"""P12.2 strict patrol scene and latent simulated observation gates."""

from pathlib import Path

import pytest

from core.enums import TaskType
from interaction.audit import CheckpointAudit
from interaction.session import MissionSession
from scenarios.compiler import compile_reference_graph
from scenarios.latent import SimulatedFireSource, load_latent_incident_fixture
from scenarios.scene import load_scene
from validator.hashing import scene_hash

SCENARIOS = Path(__file__).parents[1] / "scenarios"
PATROL = SCENARIOS / "patrol_park.yaml"
LATENT = SCENARIOS / "patrol_zone_b_fire.yaml"


def _checkpoint(*completed_now: str, now: float = 40.0) -> CheckpointAudit:
    return CheckpointAudit(
        session_id="PATROL",
        simulation_time=now,
        completed_now=list(completed_now),
        completed=list(completed_now),
        running={},
        ready_tasks=[],
        active_assignments={},
        mode="mock",
    )


def test_patrol_scene_starts_with_no_known_incident_and_only_recon_tasks():
    scene = load_scene(PATROL)
    graph = compile_reference_graph(
        scene,
        [(TaskType.AREA_RECON, zone_id) for zone_id in sorted(scene.zones)],
        [],
    )

    assert scene.incidents == {}
    assert len(graph) == 4
    assert {task.task_type for task in graph.tasks} == {TaskType.AREA_RECON}
    assert {task.target for task in graph.tasks} == set(scene.zones)


def test_loading_latent_fixture_changes_neither_scene_hash_nor_llm_context():
    scene = load_scene(PATROL)
    session = MissionSession("PATROL", scene)
    before = scene_hash(scene), session.context_for_llm()

    fixture = load_latent_incident_fixture(LATENT, scene)

    assert (scene_hash(scene), session.context_for_llm()) == before
    assert fixture.fixture_id not in session.context_for_llm()
    assert fixture.trigger_task_id not in session.context_for_llm()
    assert not hasattr(scene, "latent_fixture")


def test_observation_is_absent_before_trigger_then_emitted_exactly_once():
    scene = load_scene(PATROL)
    fixture = load_latent_incident_fixture(LATENT, scene)
    source = SimulatedFireSource(fixture)
    owners = {fixture.trigger_task_id: "S2"}

    assert source.inspect(_checkpoint("AREA_RECON__ZONE_A"), owners) is None
    observation = source.inspect(_checkpoint(fixture.trigger_task_id, now=57.25), owners)
    assert observation.fixture_id == "simulated-fire-zone-b-v1"
    assert observation.zone_id == "ZONE_B"
    assert observation.trigger_task_id == "AREA_RECON__ZONE_B"
    assert observation.detecting_agent_id == "S2"
    assert observation.simulation_time == 57.25
    assert observation.event_type == "FIRE_DETECTED"
    assert source.inspect(_checkpoint(fixture.trigger_task_id, now=57.25), owners) is None
    assert source.inspect(_checkpoint("AREA_RECON__ZONE_C", now=90.0), owners) is None


def test_missing_detecting_owner_fails_without_consuming_the_observation():
    scene = load_scene(PATROL)
    fixture = load_latent_incident_fixture(LATENT, scene)
    source = SimulatedFireSource(fixture)
    checkpoint = _checkpoint(fixture.trigger_task_id)

    with pytest.raises(ValueError, match="detecting agent"):
        source.inspect(checkpoint, {})
    assert source.inspect(checkpoint, {fixture.trigger_task_id: "S1"}) is not None


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"fixture_id": "f", "zone_id": "ZONE_B"}, "keys mismatch"),
        (
            {
                "fixture_id": "f",
                "zone_id": "ZONE_B",
                "trigger_task_id": "AREA_RECON__ZONE_B",
                "confidence": 0.9,
            },
            "keys mismatch",
        ),
        (
            {
                "fixture_id": True,
                "zone_id": "ZONE_B",
                "trigger_task_id": "AREA_RECON__ZONE_B",
            },
            "fixture_id",
        ),
        (
            {
                "fixture_id": "f",
                "zone_id": "ZONE_UNKNOWN",
                "trigger_task_id": "AREA_RECON__ZONE_UNKNOWN",
            },
            "unknown zone",
        ),
        (
            {
                "fixture_id": "f",
                "zone_id": "ZONE_B",
                "trigger_task_id": "THERMAL_RECON__FIRE_SITE_1",
            },
            "zone AREA_RECON",
        ),
        (
            {
                "fixture_id": "f",
                "zone_id": "ZONE_B",
                "trigger_task_id": "AREA_RECON__ZONE_A",
            },
            "zone AREA_RECON",
        ),
    ],
)
def test_latent_fixture_is_strict_at_load(tmp_path, payload, message):
    import yaml

    path = tmp_path / "latent.yaml"
    path.write_text(yaml.safe_dump(payload))
    with pytest.raises(ValueError, match=message):
        load_latent_incident_fixture(path, load_scene(PATROL))
