"""Graph precision / recall for P6 (RESEARCH_CONTRACT.md §12, D-021).

``task_key = (task_type, target)`` and ``edge_key = (pred_task_key,
succ_task_key)``; priority is not part of either key (§7 derives it from the
incident). When an annotation allows several graphs the prediction is scored
against the one maximising ``(task_f1, edge_f1)`` lexicographically.
"""

from __future__ import annotations

from dataclasses import dataclass

from evaluation.annotations import RefGraph
from validator.candidate import MissionCandidate, TaskKey

_Edge = tuple[TaskKey, TaskKey]


@dataclass(frozen=True, slots=True)
class PRF:
    tp: int
    fp: int
    fn: int

    @property
    def defined(self) -> bool:
        """False when there is nothing to score (0 predicted, 0 reference) —
        e.g. edge P/R for a family-B graph. Report it as N/A, not 100%."""
        return (self.tp + self.fp + self.fn) > 0

    @property
    def precision(self) -> float:
        d = self.tp + self.fp
        return 1.0 if d == 0 else self.tp / d

    @property
    def recall(self) -> float:
        d = self.tp + self.fn
        return 1.0 if d == 0 else self.tp / d

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 0.0 if p + r == 0 else 2 * p * r / (p + r)

    def __add__(self, other: PRF) -> PRF:
        return PRF(self.tp + other.tp, self.fp + other.fp, self.fn + other.fn)


@dataclass(frozen=True, slots=True)
class GraphScore:
    tasks: PRF
    edges: PRF
    exact_match: bool
    ref_index: int  # index of the best-matching allowed graph


def _prf(pred: set, ref: set) -> PRF:
    return PRF(len(pred & ref), len(pred - ref), len(ref - pred))


def predicted_keys(candidate: MissionCandidate) -> tuple[set[TaskKey], set[_Edge]]:
    tasks = {t.key for t in candidate.tasks}
    edges = {(e.predecessor, e.successor) for e in candidate.edges}
    return tasks, edges


def score_graph(
    candidate: MissionCandidate, allowed: tuple[RefGraph, ...]
) -> GraphScore:
    if not allowed:
        raise ValueError("score_graph needs at least one allowed reference graph")
    ptasks, pedges = predicted_keys(candidate)
    best: GraphScore | None = None
    for i, ref in enumerate(allowed):
        rtasks, redges = set(ref.tasks), set(ref.edges)
        tprf, eprf = _prf(ptasks, rtasks), _prf(pedges, redges)
        cand = GraphScore(
            tasks=tprf,
            edges=eprf,
            exact_match=(ptasks == rtasks and pedges == redges),
            ref_index=i,
        )
        if best is None or (cand.tasks.f1, cand.edges.f1) > (best.tasks.f1, best.edges.f1):
            best = cand
    assert best is not None
    return best


__all__ = ["PRF", "GraphScore", "score_graph", "predicted_keys"]
