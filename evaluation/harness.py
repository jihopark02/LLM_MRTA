"""Run the LLM pipeline over the fixed P6 evaluation set and aggregate
(RESEARCH_CONTRACT.md §12, §14, D-021).

``run_all`` executes every annotation with a backend (``MockBackend`` for the
self-test, ``OpenAIBackend`` for the real evaluation), records per-case metrics
plus the reproducibility triple (scene_hash / validator_version /
resolved_models), and returns an ``EvalRun`` that ``evaluation.report`` renders.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone

from evaluation.annotations import Annotation, load_all
from evaluation.metrics import PRF, GraphScore, score_graph
from llm.pipeline import generate_mission
from scenarios.scene import Scene
from validator.candidate import MissionCandidate
from validator.hashing import VALIDATOR_VERSION, scene_hash

_AXES = ("raw", "final")


@dataclass
class CaseResult:
    id: str
    family: str
    profile: str
    command: str
    approved: bool
    attempts: int
    repaired: bool
    raw_schema_valid: bool
    raw_whole_graph_valid: bool
    repaired_whole_graph_valid: bool | None
    failure_category: str | None
    latency_s: float
    resolved_models: tuple[str, ...]
    raw_score: GraphScore | None
    final_score: GraphScore | None

    def score(self, axis: str) -> GraphScore | None:
        return self.raw_score if axis == "raw" else self.final_score


@dataclass
class AxisMetrics:
    axis: str
    scored: int
    exact_match: int
    task_micro: PRF
    edge_micro: PRF
    task_precision_mean: float
    task_recall_mean: float
    edge_precision_mean: float
    edge_recall_mean: float


@dataclass
class EvalRun:
    cases: list[CaseResult]
    scene_hash: str
    validator_version: str
    backend_kind: str
    model: str | None
    started_at: str
    finished_at: str
    directory: str | None = None

    # -- X/9 style counts --------------------------------------------
    def counts(self) -> dict[str, int]:
        n = len(self.cases)
        return {
            "n": n,
            "schema_valid": sum(c.raw_schema_valid for c in self.cases),
            "raw_whole_graph_valid": sum(c.raw_whole_graph_valid for c in self.cases),
            "repaired_whole_graph_valid": sum(
                c.repaired_whole_graph_valid is True for c in self.cases
            ),
            "approved": sum(c.approved for c in self.cases),
        }

    def failure_histogram(self) -> dict[str, int]:
        hist: dict[str, int] = {}
        for c in self.cases:
            if c.failure_category is not None:
                hist[c.failure_category] = hist.get(c.failure_category, 0) + 1
        return hist

    def latency_stats(self) -> dict[str, float]:
        xs = [c.latency_s for c in self.cases]
        if not xs:
            return {"min": 0.0, "mean": 0.0, "max": 0.0}
        return {"min": min(xs), "mean": sum(xs) / len(xs), "max": max(xs)}

    def axis(self, axis: str, cases: list[CaseResult] | None = None) -> AxisMetrics:
        assert axis in _AXES
        cases = self.cases if cases is None else cases
        scored = [c.score(axis) for c in cases if c.score(axis) is not None]
        task_micro = _sum_prf(s.tasks for s in scored)
        edge_micro = _sum_prf(s.edges for s in scored)
        return AxisMetrics(
            axis=axis,
            scored=len(scored),
            exact_match=sum(s.exact_match for s in scored),
            task_micro=task_micro,
            edge_micro=edge_micro,
            task_precision_mean=_mean(s.tasks.precision for s in scored),
            task_recall_mean=_mean(s.tasks.recall for s in scored),
            edge_precision_mean=_mean(s.edges.precision for s in scored),
            edge_recall_mean=_mean(s.edges.recall for s in scored),
        )

    def by_family(self) -> dict[str, dict[str, object]]:
        out: dict[str, dict[str, object]] = {}
        for fam in ("A", "B", "C"):
            fam_cases = [c for c in self.cases if c.family == fam]
            out[fam] = {
                "n": len(fam_cases),
                "approved": sum(c.approved for c in fam_cases),
                "raw_whole_graph_valid": sum(c.raw_whole_graph_valid for c in fam_cases),
                "final": self.axis("final", fam_cases),
            }
        return out


def _mean(xs) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def _sum_prf(prfs) -> PRF:
    total = PRF(0, 0, 0)
    for p in prfs:
        total = total + p
    return total


def _score_of(candidate: MissionCandidate | None, ann: Annotation) -> GraphScore | None:
    if candidate is None:
        return None
    return score_graph(candidate, ann.allowed_graphs)


def run_case(ann: Annotation, scene: Scene, backend, *, on_error: str = "record") -> CaseResult:
    before = len(getattr(backend, "resolved_models", ()))
    t0 = time.perf_counter()
    try:
        gen = generate_mission(ann.command, scene, backend)
    except Exception as exc:  # noqa: BLE001 - the harness must survive one bad case
        if on_error == "raise":
            raise
        latency = time.perf_counter() - t0
        resolved = tuple(getattr(backend, "resolved_models", ())[before:])
        return CaseResult(
            id=ann.id, family=ann.family, profile=ann.profile, command=ann.command,
            approved=False, attempts=0, repaired=False, raw_schema_valid=False,
            raw_whole_graph_valid=False, repaired_whole_graph_valid=None,
            failure_category=f"HARNESS_ERROR:{type(exc).__name__}", latency_s=latency,
            resolved_models=resolved, raw_score=None, final_score=None,
        )
    latency = time.perf_counter() - t0
    resolved = tuple(getattr(backend, "resolved_models", ())[before:])
    return CaseResult(
        id=ann.id, family=ann.family, profile=ann.profile, command=ann.command,
        approved=gen.approved, attempts=gen.attempts, repaired=gen.repaired,
        raw_schema_valid=gen.raw_schema_valid,
        raw_whole_graph_valid=gen.raw_whole_graph_valid,
        repaired_whole_graph_valid=gen.repaired_whole_graph_valid,
        failure_category=gen.failure_category, latency_s=latency,
        resolved_models=resolved,
        raw_score=_score_of(gen.raw_candidate, ann),
        final_score=_score_of(gen.candidate, ann),
    )


def run_all(
    scene: Scene,
    backend,
    *,
    annotations: list[Annotation] | None = None,
    on_error: str = "record",
) -> EvalRun:
    anns = load_all(scene) if annotations is None else annotations
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cases = [run_case(a, scene, backend, on_error=on_error) for a in anns]
    finished = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return EvalRun(
        cases=cases,
        scene_hash=scene_hash(scene),
        validator_version=VALIDATOR_VERSION,
        backend_kind=type(backend).__name__,
        model=getattr(backend, "model", None),
        started_at=started,
        finished_at=finished,
    )


__all__ = ["CaseResult", "AxisMetrics", "EvalRun", "run_case", "run_all"]
