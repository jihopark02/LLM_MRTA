"""Presentation figures for the extended response_district scene (D-059).

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
from core.mission_state import MissionState  # noqa: E402
from demo.visualization import (  # noqa: E402
    dag_render_spec,
    execution_map_spec,
    plan_map_spec,
    render_mission_map,
    render_task_graph,
)
from execution.executor import SimExecutor  # noqa: E402
from scenarios.fixture import load_reference_fixture  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "scenarios" / "response_district_fixture.yaml"
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


if __name__ == "__main__":
    main()
