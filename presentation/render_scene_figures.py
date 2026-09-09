"""Presentation figures for the extended scenes (response_district D-059,
demo_grid D-073).

Uses the contract's single figure path (demo.visualization.render_mission_map /
render_task_graph, §18.14). No research logic here — this script only relabels
zones to their ASCII id for the slides (the YAML keeps Korean landmark names for
natural-language grounding) and saves PNGs.

    python3 presentation/render_scene_figures.py
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
from dataclasses import replace  # noqa: E402
from pathlib import Path  # noqa: E402

from allocation.allocate import allocate  # noqa: E402
from core.enums import TaskType  # noqa: E402
from core.mission_state import MissionState  # noqa: E402
from demo.visualization import (  # noqa: E402
    dag_render_spec,
    execution_map_spec,
    plan_map_spec,
    render_mission_map,
    render_task_graph,
    world_map_spec,
)
from execution.executor import SimExecutor  # noqa: E402
from scenarios.compiler import compile_reference_graph  # noqa: E402
from scenarios.fixture import load_reference_fixture  # noqa: E402
from scenarios.scene import load_scene  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "scenarios" / "response_district_fixture.yaml"
GRID_SCENE = ROOT / "scenarios" / "demo_grid.yaml"
OUT = ROOT / "presentation"


def _ascii_zone_labels(scene):
    """Slide figures show the zone id, not the Korean landmark name."""
    scene.zones = {
        zid: replace(zone, name=zid) for zid, zone in scene.zones.items()
    }


def main() -> None:
    loaded = load_reference_fixture(FIXTURE)
    scene, graph = loaded.scene, loaded.graph
    _ascii_zone_labels(scene)

    state = MissionState(graph=graph.clone(), agents={a.agent_id: a for a in scene.fleet})
    plan = allocate(state, scene)
    result = SimExecutor(
        MissionState(graph=graph.clone(), agents={a.agent_id: a for a in scene.fleet}),
        scene,
    ).run()

    figures = {
        "response_district_dag.png": render_task_graph(dag_render_spec(graph)),
        "response_district_plan_map.png": render_mission_map(plan_map_spec(scene, graph, plan)),
        "response_district_execution_map.png": render_mission_map(
            execution_map_spec(scene, graph, result)
        ),
    }
    for name, fig in figures.items():
        fig.savefig(OUT / name, dpi=150, bbox_inches="tight")
        print("wrote", OUT / name)
    print(f"plan makespan {plan.estimated_makespan:.1f} · exec {result.termination.value} "
          f"{result.makespan:.1f} · assignments {len(plan.assignments)}")

    _demo_grid_figures()


def _demo_grid_figures() -> None:
    """demo_grid (D-073): the bare world, and a 15-zone recon plan so the CBBA
    task distribution across the 3 UAVs is visible. Fires are latent, so there
    is no incident workflow in this figure."""
    scene = load_scene(GRID_SCENE)
    graph = compile_reference_graph(
        scene, [(TaskType.AREA_RECON, zid) for zid in sorted(scene.zones)], []
    )
    state = MissionState(graph=graph.clone(), agents={a.agent_id: a for a in scene.fleet})
    plan = allocate(state, scene)
    figures = {
        "demo_grid_world_map.png": render_mission_map(world_map_spec(scene)),
        "demo_grid_plan_map.png": render_mission_map(plan_map_spec(scene, graph, plan)),
    }
    for name, fig in figures.items():
        fig.savefig(OUT / name, dpi=150, bbox_inches="tight")
        print("wrote", OUT / name)
    split = {
        aid: sum(1 for a in plan.assignments.values() if a == aid)
        for aid in sorted({*plan.assignments.values()})
    }
    print(f"demo_grid plan makespan {plan.estimated_makespan:.1f} · UAV split {split}")


if __name__ == "__main__":
    main()
