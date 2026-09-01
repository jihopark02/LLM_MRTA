"""Reference fixture loader (RESEARCH_CONTRACT.md §3 fixed shape, §12 Family A).

Loads the semantic scene plus a hand-authored task fixture and compiles them
into a TaskGraph via the deterministic compiler. The P1 completion gate checks
this graph's shape (see tests/test_reference_fixture.py).
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

from core.enums import PlatformKind, TaskType
from core.task_graph import TaskGraph
from scenarios.compiler import TASK_TABLE, compile_graph, task_id_for
from scenarios.scene import Scene, load_scene

_SCENES_DIR = Path(__file__).parent


def _parse_endpoint(text: str) -> tuple[TaskType, str]:
    type_str, target = text.split(":", 1)
    return TaskType(type_str.strip()), target.strip()


@dataclass(slots=True)
class LoadedFixture:
    fixture_id: str
    scene: Scene
    graph: TaskGraph

    def ugv_target_nodes(self) -> dict[str, str]:
        """task_id -> incident access node, for every UGV-targeted task (§8)."""
        out: dict[str, str] = {}
        for task in self.graph.tasks:
            if PlatformKind.UGV in task.eligible_platforms:
                out[task.task_id] = self.scene.incidents[task.target].access_node
        return out


def load_reference_fixture(
    fixture_path: str | Path = _SCENES_DIR / "reference_fixture.yaml",
) -> LoadedFixture:
    raw = yaml.safe_load(Path(fixture_path).read_text())
    scene = load_scene(_SCENES_DIR / f"{raw['scene']}.yaml")

    task_specs = [
        (TaskType(t["type"]), t["target"], int(t["priority"])) for t in raw["tasks"]
    ]
    edges = [
        (_parse_endpoint(pred), _parse_endpoint(succ)) for pred, succ in raw["edges"]
    ]
    graph = compile_graph(scene, task_specs, edges)
    return LoadedFixture(raw["fixture_id"], scene, graph)


def eligible_bidder_counts(scene: Scene) -> dict[TaskType, int]:
    """Number of fleet agents that could bid on each task type (contract §5)."""
    return {
        tt: len(scene.eligible_agents(spec.required_capabilities, spec.eligible_platforms))
        for tt, spec in TASK_TABLE.items()
    }


__all__ = [
    "LoadedFixture",
    "load_reference_fixture",
    "eligible_bidder_counts",
    "task_id_for",
]
