"""Smoke test for the demo_grid native default scene (D-073).

Not a research gate — demo_grid produces no evaluation numbers (§3.1). This
only pins the things a live demo depends on: the 15-zone scene loads, the
world is shown before any mission, the seeded latent fires stay hidden until
recon reaches them, and the bare letter labels still ground.
"""

from pathlib import Path

import pytest

from interaction.ground import resolve_zone
from scenarios.latent import load_latent_fire_field
from scenarios.scene import load_scene

SCENARIOS = Path(__file__).parents[1] / "scenarios"
GRID = SCENARIOS / "demo_grid.yaml"
GRID_LATENT = SCENARIOS / "demo_grid_latent.yaml"


@pytest.fixture
def scene():
    return load_scene(GRID)


def test_demo_grid_loads_with_15_zones_and_the_standard_fleet(scene):
    assert scene.scene_id == "demo_grid"
    assert sorted(scene.zones) == [f"ZONE_{c}" for c in "ABCDEFGHIJKLMNO"]
    assert scene.incidents == {}
    kinds = sorted(a.platform_kind.value for a in scene.fleet)
    assert kinds == ["UAV", "UAV", "UAV", "UGV", "UGV"]
    # all UGV start nodes and every zone response node are in the route graph
    # (load_scene raises otherwise) — assert the fleet launch point too
    ugv_starts = {scene.agent_access_nodes[a.agent_id]
                  for a in scene.fleet if a.platform_kind.value == "UGV"}
    assert ugv_starts == {"R_DEPOT"}


def test_world_map_before_any_mission_has_no_mission_overlay_and_no_fires(scene):
    from demo.visualization import world_map_spec

    spec = world_map_spec(scene)
    assert spec.mode == "world"
    assert {z.entity_id for z in spec.zones} == set(scene.zones)
    assert {a.agent_id for a in spec.agents} == {a.agent_id for a in scene.fleet}
    assert spec.route_lanes
    assert spec.incidents == ()          # latent fires are not in scene.incidents
    assert spec.legs == () and spec.task_points == ()


def test_seeded_latent_fires_are_hidden_until_recon_and_reproducible(scene):
    field = load_latent_fire_field(GRID_LATENT, scene)

    # deterministic, spread (min_separation 170 in the spec)
    assert field.zone_ids == ("ZONE_A", "ZONE_D", "ZONE_J", "ZONE_O")
    assert load_latent_fire_field(GRID_LATENT, scene).zone_ids == field.zone_ids

    # the field never touches the scene: still incident-empty, hash unchanged
    from validator.hashing import scene_hash
    assert scene.incidents == {}
    assert scene_hash(scene) == scene_hash(load_scene(GRID))

    # every trigger is that zone's AREA_RECON completion, nothing earlier
    assert [f.trigger_task_id for f in field.fixtures] == [
        f"AREA_RECON__{z}" for z in field.zone_ids
    ]


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("ZONE_A", "ZONE_A"),
        ("A", "ZONE_A"),
        ("A 구역", "ZONE_A"),
        ("Zone A", "ZONE_A"),
        ("O 구역에서", "ZONE_O"),
        ("zone_k", "ZONE_K"),
    ],
)
def test_bare_letter_labels_still_ground(scene, phrase, expected):
    out = resolve_zone(scene, phrase)
    assert out.resolved and out.entity_id == expected


def test_demo_grid_controller_opens_on_the_world(tmp_path):
    from desktop.controller import DesktopController

    controller = DesktopController(runtime_root=tmp_path, frame_count=4)
    assert controller.scenario_id == "demo-grid"
    assert controller.session.state is None

    spec = controller.current_map_spec()
    assert spec.mode == "world"
    assert spec.incidents == ()          # A/D/J/O not revealed yet
    assert len(spec.zones) == 15
