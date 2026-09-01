"""Human-authored reference annotations for P6 (RESEARCH_CONTRACT.md §12, D-021).

Each ``data/reference_annotations/<id>.yaml`` fixes, BEFORE any LLM is called,
one evaluation case: the NL command and the set of allowed canonical task
graphs it may produce. Git history is the proof of ordering — these files are
committed in the same commit as D-021, ahead of every eval run.

A graph is written compactly:

    recon_zones: [ZONE_A, ZONE_B]          # -> AREA_RECON tasks, no edges
    incident_chains:
      FIRE_SITE_1: [THERMAL_RECON, SUPPRESSANT_DROP]   # contiguous §4 prefix

The chain expands to one task per step plus the sequential edges between them.
An explicit ``tasks:`` / ``edges:`` form is also accepted (unused by the fixed
nine, kept for future cases). Every allowed graph is checked against the
deterministic Validator at load time, so a mis-authored reference fails loudly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from core.enums import TaskType
from scenarios.scene import Scene
from validator.candidate import CandidateEdge, CandidateTask, MissionCandidate, TaskKey
from validator.validate import validate_candidate

# priority is scene-derived (D-022) and not part of task_key or the candidate,
# so annotations never carry it.

_DIR = Path(__file__).resolve().parents[1] / "data" / "reference_annotations"
CASE_IDS: tuple[str, ...] = ("A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2", "C3")
_FAMILIES = {"A", "B", "C"}
_PROFILES = {"FULL_RESPONSE", "AERIAL_ONLY", "SELECTIVE_RESPONSE"}

# §4 incident workflow, head first.
WORKFLOW_CHAIN: tuple[TaskType, ...] = (
    TaskType.THERMAL_RECON,
    TaskType.SUPPRESSANT_DROP,
    TaskType.GROUND_INSPECTION,
    TaskType.GROUND_SUPPRESSION,
)

_Edge = tuple[TaskKey, TaskKey]


@dataclass(frozen=True, slots=True)
class RefGraph:
    tasks: frozenset[TaskKey]
    edges: frozenset[_Edge]


@dataclass(frozen=True, slots=True)
class Annotation:
    id: str
    family: str
    profile: str
    command: str
    rationale: str
    allowed_graphs: tuple[RefGraph, ...]


def _key(text: str) -> TaskKey:
    tt, _, target = text.partition(":")
    return (TaskType(tt.strip()), target.strip())


def _expand(spec: dict, scene: Scene) -> tuple[RefGraph, MissionCandidate]:
    unknown = set(spec) - {"recon_zones", "incident_chains", "tasks", "edges"}
    if unknown:
        raise ValueError(f"allowed_graph has unexpected keys {sorted(unknown)}")

    tasks: list[CandidateTask] = []
    edges: list[CandidateEdge] = []

    for zone in spec.get("recon_zones") or []:
        if zone not in scene.zones:
            raise ValueError(f"recon_zones: {zone!r} is not a scene zone")
        tasks.append(CandidateTask(TaskType.AREA_RECON, zone))

    for incident, chain in (spec.get("incident_chains") or {}).items():
        if incident not in scene.incidents:
            raise ValueError(f"incident_chains: {incident!r} is not a scene incident")
        steps = tuple(TaskType(s) for s in chain)
        if steps != WORKFLOW_CHAIN[: len(steps)]:
            raise ValueError(
                f"incident_chains[{incident}] {list(chain)} is not a contiguous prefix "
                f"of {[t.value for t in WORKFLOW_CHAIN]}"
            )
        for step in steps:
            tasks.append(CandidateTask(step, incident))
        for pred, succ in zip(steps, steps[1:], strict=False):
            edges.append(CandidateEdge((pred, incident), (succ, incident)))

    for entry in spec.get("tasks") or []:
        if set(entry) != {"task_type", "target"} or not isinstance(entry["target"], str):
            raise ValueError(f"explicit task entry must be {{task_type, target}}: {entry}")
        tasks.append(CandidateTask(TaskType(entry["task_type"]), entry["target"]))
    for pred, succ in spec.get("edges") or []:
        edges.append(CandidateEdge(_key(pred), _key(succ)))

    task_keys = frozenset(t.key for t in tasks)
    if len(task_keys) != len(tasks):
        raise ValueError("allowed_graph has duplicate task keys")
    graph = RefGraph(task_keys, frozenset((e.predecessor, e.successor) for e in edges))
    return graph, MissionCandidate(tasks, edges)


def load_annotation(
    path: str | Path, scene: Scene, *, self_check: bool = True
) -> Annotation:
    raw = yaml.safe_load(Path(path).read_text())
    expected = {"id", "family", "profile", "command", "rationale", "allowed_graphs"}
    if set(raw) != expected:
        raise ValueError(f"{path}: keys {sorted(raw)} != {sorted(expected)}")
    if raw["family"] not in _FAMILIES:
        raise ValueError(f"{path}: family {raw['family']!r}")
    if raw["profile"] not in _PROFILES:
        raise ValueError(f"{path}: profile {raw['profile']!r}")
    if not raw["allowed_graphs"]:
        raise ValueError(f"{path}: allowed_graphs is empty")

    graphs: list[RefGraph] = []
    for spec in raw["allowed_graphs"]:
        graph, candidate = _expand(spec, scene)
        if self_check:
            result = validate_candidate(candidate, scene)
            if not result.accepted:
                raise ValueError(
                    f"{path}: a canonical allowed_graph fails the Validator: "
                    f"{[str(e) for e in result.errors]}"
                )
        graphs.append(graph)

    return Annotation(
        id=raw["id"],
        family=raw["family"],
        profile=raw["profile"],
        command=" ".join(raw["command"].split()),
        rationale=" ".join(raw["rationale"].split()),
        allowed_graphs=tuple(graphs),
    )


def load_all(scene: Scene, *, directory: str | Path = _DIR) -> list[Annotation]:
    directory = Path(directory)
    out = [load_annotation(directory / f"{cid}.yaml", scene) for cid in CASE_IDS]
    if [a.id for a in out] != list(CASE_IDS):
        raise ValueError(f"annotation ids {[a.id for a in out]} != {list(CASE_IDS)}")
    return out


__all__ = [
    "Annotation",
    "RefGraph",
    "WORKFLOW_CHAIN",
    "CASE_IDS",
    "load_annotation",
    "load_all",
]
