"""Seeded multi latent fire field gates (§22.2, D-062)."""

from pathlib import Path

import pytest
import yaml

from interaction.audit import CheckpointAudit
from interaction.session import MissionSession
from scenarios.latent import (
    SimulatedFireField,
    load_latent_fire_field,
)
from scenarios.scene import load_scene
from validator.hashing import scene_hash

SCENARIOS = Path(__file__).parents[1] / "scenarios"
DISTRICT = SCENARIOS / "response_district_patrol.yaml"
FIELD = SCENARIOS / "response_district_latent.yaml"


def _spec(tmp_path, **overrides) -> Path:
    payload = {"field_id": "test-field", "seed": 99, "count": 2}
    payload.update(overrides)
    path = tmp_path / "field.yaml"
    path.write_text(yaml.safe_dump(payload))
    return path


def _checkpoint(*completed_now: str, now: float = 40.0) -> CheckpointAudit:
    return CheckpointAudit(
        session_id="DISTRICT",
        simulation_time=now,
        completed_now=list(completed_now),
        completed=list(completed_now),
        running={},
        ready_tasks=[],
        active_assignments={},
        mode="mock",
    )


def test_same_seed_and_spec_pick_the_same_zones_every_load():
    scene = load_scene(DISTRICT)
    first = load_latent_fire_field(FIELD, scene)
    second = load_latent_fire_field(FIELD, scene)

    assert first.zone_ids == second.zone_ids
    assert len(first.zone_ids) == 2
    assert set(first.zone_ids) <= set(scene.zones)
    assert first.zone_ids == tuple(sorted(first.zone_ids))
    assert [fixture.trigger_task_id for fixture in first.fixtures] == [
        f"AREA_RECON__{zone_id}" for zone_id in first.zone_ids
    ]


def test_the_seed_is_what_chooses_the_zones(tmp_path):
    scene = load_scene(DISTRICT)
    a = load_latent_fire_field(_spec(tmp_path, seed=1), scene).zone_ids
    b = load_latent_fire_field(_spec(tmp_path, seed=2), scene).zone_ids
    c = load_latent_fire_field(_spec(tmp_path, seed=1), scene).zone_ids

    assert a == c
    assert a != b  # not guaranteed in general, but true for these two seeds


def test_candidate_zones_restrict_the_pool(tmp_path):
    scene = load_scene(DISTRICT)
    field = load_latent_fire_field(
        _spec(tmp_path, candidate_zones=["ZONE_C", "ZONE_F"], count=2), scene
    )
    assert set(field.zone_ids) == {"ZONE_C", "ZONE_F"}


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"count": 99}, "exceeds"),
        ({"count": 0}, "count must be"),
        ({"count": True}, "count must be"),
        ({"seed": "99"}, "seed must be"),
        ({"candidate_zones": ["ZONE_C", "ZONE_NOPE"]}, "unknown zones"),
        ({"candidate_zones": ["ZONE_C", "ZONE_C"]}, "duplicate"),
    ],
)
def test_field_spec_is_strict_at_load(tmp_path, overrides, message):
    with pytest.raises(ValueError, match=message):
        load_latent_fire_field(_spec(tmp_path, **overrides), load_scene(DISTRICT))


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"field_id": "f", "seed": 1}, "keys mismatch"),
        ({"field_id": "f", "seed": 1, "count": 2, "extra": 1}, "keys mismatch"),
    ],
)
def test_field_spec_rejects_missing_or_unknown_keys(tmp_path, payload, message):
    path = tmp_path / "field.yaml"
    path.write_text(yaml.safe_dump(payload))
    with pytest.raises(ValueError, match=message):
        load_latent_fire_field(path, load_scene(DISTRICT))


def test_loading_a_field_changes_neither_scene_hash_nor_llm_context():
    scene = load_scene(DISTRICT)
    session = MissionSession("DISTRICT", scene)
    before = scene_hash(scene), session.context_for_llm()

    field = load_latent_fire_field(FIELD, scene)

    assert (scene_hash(scene), session.context_for_llm()) == before
    assert field.field_id not in session.context_for_llm()
    for fixture in field.fixtures:
        assert fixture.fixture_id not in session.context_for_llm()
        assert fixture.trigger_task_id not in session.context_for_llm()
    assert not hasattr(scene, "latent_field")


def test_field_source_reveals_each_fixture_once():
    scene = load_scene(DISTRICT)
    field = load_latent_fire_field(FIELD, scene)
    source = SimulatedFireField(field)
    first, second = field.zone_ids
    owners = {fixture.trigger_task_id: "U1" for fixture in field.fixtures}

    assert source.inspect(_checkpoint("AREA_RECON__ZONE_ZZZ"), owners) == ()

    revealed = source.inspect(_checkpoint(f"AREA_RECON__{first}", now=50.0), owners)
    assert [obs.zone_id for obs in revealed] == [first]
    assert source.inspect(_checkpoint(f"AREA_RECON__{first}", now=50.0), owners) == ()

    revealed = source.inspect(_checkpoint(f"AREA_RECON__{second}", now=80.0), owners)
    assert [obs.zone_id for obs in revealed] == [second]


def test_two_triggers_in_one_checkpoint_reveal_in_zone_id_order():
    scene = load_scene(DISTRICT)
    field = load_latent_fire_field(FIELD, scene)
    source = SimulatedFireField(field)
    owners = {fixture.trigger_task_id: "U2" for fixture in field.fixtures}
    triggers = [f"AREA_RECON__{zone_id}" for zone_id in reversed(field.zone_ids)]

    revealed = source.inspect(_checkpoint(*triggers, now=61.0), owners)

    assert [obs.zone_id for obs in revealed] == sorted(field.zone_ids)
