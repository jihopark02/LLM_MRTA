"""Run the LLM pipeline over the fixed P6 evaluation set and aggregate
(RESEARCH_CONTRACT.md §12, §14, D-021, D-022).

``run_all`` executes every annotation with a backend (``MockBackend`` for the
self-test, ``OpenAIBackend`` for the real evaluation) and returns an ``EvalRun``.
Each ``CaseResult`` keeps the full audit trail — raw and final candidate
contents (task_type / target / derived priority), edges, graph_hash, accepted,
error_codes — so a third party can recompute every metric from ``task_type`` and
``target`` alone (§12, §16). Harness-level failures (network, auth, a backend
that raises) are recorded in ``harness_error``, kept separate from the model's
own ``failure_category``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone

from evaluation.annotations import Annotation, load_all
from evaluation.metrics import PRF, GraphScore, score_graph
from llm.pipeline import GenerationResult, generate_mission
from scenarios.compiler import derive_priority
from scenarios.scene import Scene
from validator.candidate import MissionCandidate, key_str
from validator.hashing import VALIDATOR_VERSION, scene_hash
from validator.result import ValidationResult

_AXES = ("raw", "final")


@dataclass
class GraphSnapshot:
    """A candidate as scored + audited, everything a reader needs to recompute."""

    tasks: list[dict]  # {task_type, target, priority(derived)}
    edges: list[list[str]]  # ["TYPE:target", "TYPE:target"]
    graph_hash: str
    accepted: bool
    error_codes: list[str]


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
    repaired_schema_valid: bool | None
    repaired_whole_graph_valid: bool | None
    failure_category: str | None
    harness_error: str | None
    pipeline_errors: list[dict]  # structured GenerationResult.errors (code/subject/detail)
    latency_s: float
    resolved_models: tuple[str, ...]
    raw: GraphSnapshot | None
    final: GraphSnapshot | None
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
    edge_precision_mean: float | None  # None when no case has a scorable edge set
    edge_recall_mean: float | None


@dataclass
class EvalRun:
    cases: list[CaseResult]
    scene_hash: str
    validator_version: str
    backend_kind: str
    model: str | None
    started_at: str
    finished_at: str

    def counts(self) -> dict[str, int]:
        c = self.cases
        return {
            "n": len(c),
            "schema_valid": sum(x.raw_schema_valid for x in c),
            "raw_whole_graph_valid": sum(x.raw_whole_graph_valid for x in c),
            "approved": sum(x.approved for x in c),
            "harness_errors": sum(x.harness_error is not None for x in c),
        }

    def repair_counts(self) -> dict[str, int]:
        c = self.cases
        attempted = sum(x.repaired for x in c)
        return {
            "attempted": attempted,
            "recovered": sum(x.repaired and x.approved for x in c),
            "first_pass_approved": sum(x.approved and not x.repaired for x in c),
        }

    def failure_histogram(self) -> dict[str, int]:
        hist: dict[str, int] = {}
        for x in self.cases:
            if x.failure_category is not None:
                hist[x.failure_category] = hist.get(x.failure_category, 0) + 1
        return hist

    def latency_stats(self) -> dict[str, float]:
        xs = [x.latency_s for x in self.cases]
        if not xs:
            return {"min": 0.0, "mean": 0.0, "max": 0.0}
        return {"min": min(xs), "mean": sum(xs) / len(xs), "max": max(xs)}

    def axis(self, axis: str, cases: list[CaseResult] | None = None) -> AxisMetrics:
        assert axis in _AXES
        cases = self.cases if cases is None else cases
        scored = [c.score(axis) for c in cases if c.score(axis) is not None]
        edge_defined = [s.edges for s in scored if s.edges.defined]
        return AxisMetrics(
            axis=axis,
            scored=len(scored),
            exact_match=sum(s.exact_match for s in scored),
            task_micro=_sum_prf(s.tasks for s in scored),
            edge_micro=_sum_prf(s.edges for s in scored),
            task_precision_mean=_mean(s.tasks.precision for s in scored),
            task_recall_mean=_mean(s.tasks.recall for s in scored),
            edge_precision_mean=_mean(p.precision for p in edge_defined) if edge_defined else None,
            edge_recall_mean=_mean(p.recall for p in edge_defined) if edge_defined else None,
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


def snapshot(
    scene: Scene, candidate: MissionCandidate | None, validation: ValidationResult | None
) -> GraphSnapshot | None:
    if candidate is None:
        return None
    tasks = [
        {
            "task_type": t.task_type.value,
            "target": t.target,
            "priority": _safe_priority(scene, t.task_type, t.target),
        }
        for t in candidate.tasks
    ]
    edges = [[key_str(e.predecessor), key_str(e.successor)] for e in candidate.edges]
    return GraphSnapshot(
        tasks=tasks,
        edges=edges,
        graph_hash=validation.graph_hash if validation else "",
        accepted=bool(validation and validation.accepted),
        error_codes=[c.value for c in validation.error_codes] if validation else [],
    )


def _safe_priority(scene: Scene, task_type, target) -> int | None:
    try:
        return derive_priority(scene, task_type, target)
    except ValueError:
        return None


def _score(candidate: MissionCandidate | None, ann: Annotation) -> GraphScore | None:
    return None if candidate is None else score_graph(candidate, ann.allowed_graphs)


def _case_from_generation(
    ann: Annotation, scene: Scene, gen: GenerationResult, latency: float, resolved: tuple[str, ...]
) -> CaseResult:
    return CaseResult(
        id=ann.id, family=ann.family, profile=ann.profile, command=ann.command,
        approved=gen.approved, attempts=gen.attempts, repaired=gen.repaired,
        raw_schema_valid=gen.raw_schema_valid,
        raw_whole_graph_valid=gen.raw_whole_graph_valid,
        repaired_schema_valid=gen.repaired_schema_valid,
        repaired_whole_graph_valid=gen.repaired_whole_graph_valid,
        failure_category=gen.failure_category, harness_error=None,
        pipeline_errors=[
            {"code": e.code.value, "subject": e.subject, "detail": e.detail}
            for e in gen.errors
        ],
        latency_s=latency, resolved_models=resolved,
        raw=snapshot(scene, gen.raw_candidate, gen.raw_validation),
        final=snapshot(scene, gen.candidate, gen.validation),
        raw_score=_score(gen.raw_candidate, ann),
        final_score=_score(gen.candidate, ann),
    )


def run_case(ann: Annotation, scene: Scene, backend, *, on_error: str = "record") -> CaseResult:
    before = len(getattr(backend, "resolved_models", ()))
    t0 = time.perf_counter()
    try:
        gen = generate_mission(ann.command, scene, backend)
    except Exception as exc:  # noqa: BLE001 - the harness must survive one bad case
        if on_error == "raise":
            raise
        resolved = tuple(getattr(backend, "resolved_models", ())[before:])
        return CaseResult(
            id=ann.id, family=ann.family, profile=ann.profile, command=ann.command,
            approved=False, attempts=0, repaired=False, raw_schema_valid=False,
            raw_whole_graph_valid=False, repaired_schema_valid=None,
            repaired_whole_graph_valid=None, failure_category=None,
            harness_error=f"{type(exc).__name__}: {exc}", pipeline_errors=[],
            latency_s=time.perf_counter() - t0, resolved_models=resolved,
            raw=None, final=None, raw_score=None, final_score=None,
        )
    latency = time.perf_counter() - t0
    resolved = tuple(getattr(backend, "resolved_models", ())[before:])
    return _case_from_generation(ann, scene, gen, latency, resolved)


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


__all__ = [
    "CaseResult", "GraphSnapshot", "AxisMetrics", "EvalRun",
    "run_case", "run_all", "snapshot",
]
