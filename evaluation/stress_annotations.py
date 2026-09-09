"""Loader for the D-074 pre-registered stress sets (RESEARCH_CONTRACT.md §12).

Separate from ``evaluation/annotations.py`` (the frozen P6 set) — this one adds
``expect`` (approve / reject / safety-invariant) and an ``adoption`` flag
(gated / diagnostic) on top of the shared P6 compact graph notation
(``evaluation.annotations.expand_graph_spec``). Nothing here calls a model.

    linguistic/  19 cases  L01..L19  — industrial_park (same scene as P6)
    scale/       15 cases  S01..S15  — stress_grid (15 zone / 4 incident)

Each YAML is frozen before the live A/B (D-074): after that commit the command,
allowed graphs and reject category are not edited in response to results.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from evaluation.annotations import RefGraph, expand_graph_spec
from scenarios.scene import Scene
from validator.validate import validate_candidate

_DIR = Path(__file__).resolve().parents[1] / "data" / "stress_annotations"

SET_DIR = {"linguistic": "linguistic", "scale": "scale"}
SET_SCENE = {"linguistic": "industrial_park.yaml", "scale": "stress_grid.yaml"}
CASE_IDS = {
    "linguistic": tuple(f"L{i:02d}" for i in range(1, 20)),   # L01..L19
    "scale": tuple(f"S{i:02d}" for i in range(1, 16)),        # S01..S15
}

_EXPECT = {"approve", "reject", "safety-invariant"}
_ADOPTION = {"gated", "diagnostic"}
_FAILURE_CATEGORIES = {"SCHEMA", "WORKFLOW", "STRUCTURE", "REFERENCE", "FEASIBILITY", "OTHER"}
_REQUIRED = {"id", "set", "category", "command", "rationale", "expect"}
_OPTIONAL = {"adoption", "allowed_graphs", "reject_category", "mock_graph"}


@dataclass(frozen=True, slots=True)
class StressCase:
    id: str
    set: str
    category: str
    command: str
    rationale: str
    expect: str                       # approve | reject | safety-invariant
    adoption: str                     # gated | diagnostic
    allowed_graphs: tuple[RefGraph, ...]
    reject_category: str | None
    # The raw graph a MockBackend emits for --mock smoke runs. approve cases
    # derive it from allowed_graphs[0]; reject / safety-invariant cases give it
    # explicitly (it deliberately references a missing target or omits a
    # prerequisite, which the Validator then catches).
    mock_graph: dict | None

    @property
    def gated(self) -> bool:
        return self.adoption == "gated"


def load_case(path: str | Path, scene: Scene) -> StressCase:
    raw = yaml.safe_load(Path(path).read_text())
    keys = set(raw)
    if not _REQUIRED <= keys or not keys <= (_REQUIRED | _OPTIONAL):
        raise ValueError(f"{path}: keys {sorted(keys)} (need {sorted(_REQUIRED)})")
    if raw["expect"] not in _EXPECT:
        raise ValueError(f"{path}: expect {raw['expect']!r} not in {sorted(_EXPECT)}")
    adoption = raw.get("adoption", "gated")
    if adoption not in _ADOPTION:
        raise ValueError(f"{path}: adoption {adoption!r}")

    graphs: list[RefGraph] = []
    for spec in raw.get("allowed_graphs") or []:
        graph, candidate = expand_graph_spec(spec, scene)
        result = validate_candidate(candidate, scene)
        if not result.accepted:
            raise ValueError(
                f"{path}: an allowed_graph fails the Validator: "
                f"{[str(e) for e in result.errors]}"
            )
        graphs.append(graph)

    reject_category = raw.get("reject_category")
    mock_graph = raw.get("mock_graph")
    if raw["expect"] == "reject":
        if reject_category not in _FAILURE_CATEGORIES:
            raise ValueError(
                f"{path}: reject case needs reject_category in {sorted(_FAILURE_CATEGORIES)}"
            )
        if graphs:
            raise ValueError(f"{path}: a reject case must not carry allowed_graphs")
    elif raw["expect"] == "approve" and not graphs:
        raise ValueError(f"{path}: an approve case needs at least one allowed_graph")
    if raw["expect"] in {"reject", "safety-invariant"} and not (
        isinstance(mock_graph, dict) and "tasks" in mock_graph
    ):
        raise ValueError(f"{path}: {raw['expect']} case needs a mock_graph with tasks")

    return StressCase(
        id=raw["id"],
        set=raw["set"],
        category=raw["category"],
        command=" ".join(raw["command"].split()),
        rationale=" ".join(raw["rationale"].split()),
        expect=raw["expect"],
        adoption=adoption,
        allowed_graphs=tuple(graphs),
        reject_category=reject_category,
        mock_graph=mock_graph,
    )


def load_stress_set(set_name: str, scene: Scene) -> list[StressCase]:
    if set_name not in CASE_IDS:
        raise ValueError(f"unknown stress set {set_name!r}")
    directory = _DIR / SET_DIR[set_name]
    cases = [load_case(directory / f"{cid}.yaml", scene) for cid in CASE_IDS[set_name]]
    ids = [c.id for c in cases]
    if ids != list(CASE_IDS[set_name]):
        raise ValueError(f"{set_name}: ids {ids} != {list(CASE_IDS[set_name])}")
    for c in cases:
        if c.set != set_name:
            raise ValueError(f"{c.id}: set field {c.set!r} != {set_name!r}")
    return cases


__all__ = ["StressCase", "CASE_IDS", "SET_SCENE", "load_case", "load_stress_set"]
