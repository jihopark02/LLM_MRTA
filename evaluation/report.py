"""Render a P6 ``EvalRun`` as a raw-count table and as JSON
(RESEARCH_CONTRACT.md §12, §14, D-021).

Small-sample results are reported with raw counts ("7/9 valid", "family A:
2/3"), never bare percentages.
"""

from __future__ import annotations

import json

from evaluation.harness import AxisMetrics, EvalRun

_N = 9  # the fixed evaluation set size


def _axis_block(m: AxisMetrics) -> list[str]:
    return [
        f"  {m.axis:<6} scored {m.scored}/{_N}   exact-match {m.exact_match}/{m.scored}",
        f"         task  P/R (macro) {m.task_precision_mean:.2f}/{m.task_recall_mean:.2f}"
        f"   micro tp/fp/fn {m.task_micro.tp}/{m.task_micro.fp}/{m.task_micro.fn}",
        f"         edge  P/R (macro) {m.edge_precision_mean:.2f}/{m.edge_recall_mean:.2f}"
        f"   micro tp/fp/fn {m.edge_micro.tp}/{m.edge_micro.fp}/{m.edge_micro.fn}",
    ]


def text_report(run: EvalRun) -> str:
    c = run.counts()
    lat = run.latency_stats()
    lines: list[str] = []
    lines.append("P6 LLM mission-decomposition evaluation (RESEARCH_CONTRACT.md §12)")
    lines.append("=" * 66)
    lines.append(f"backend        {run.backend_kind}" + (f" ({run.model})" if run.model else ""))
    lines.append(f"scene_hash     {run.scene_hash}")
    lines.append(f"validator      {run.validator_version}")
    lines.append(f"run            {run.started_at} .. {run.finished_at}")
    lines.append("")
    lines.append("counts (X/9)")
    lines.append(f"  schema-valid                 {c['schema_valid']}/{_N}")
    lines.append(f"  raw whole-graph-valid        {c['raw_whole_graph_valid']}/{_N}")
    lines.append(f"  whole-graph-valid after repair {c['repaired_whole_graph_valid']}/{_N}")
    lines.append(f"  approved                     {c['approved']}/{_N}")
    lines.append("")
    lines.append("graph metrics (against best-matching allowed reference)")
    for axis in ("raw", "final"):
        lines.extend(_axis_block(run.axis(axis)))
    lines.append("")
    lines.append("by family (final)")
    for fam, d in run.by_family().items():
        m: AxisMetrics = d["final"]  # type: ignore[assignment]
        lines.append(
            f"  {fam}: approved {d['approved']}/{d['n']}   "
            f"raw-valid {d['raw_whole_graph_valid']}/{d['n']}   "
            f"exact {m.exact_match}/{m.scored}   "
            f"task P/R {m.task_precision_mean:.2f}/{m.task_recall_mean:.2f}   "
            f"edge P/R {m.edge_precision_mean:.2f}/{m.edge_recall_mean:.2f}"
        )
    lines.append("")
    hist = run.failure_histogram()
    hist_str = ", ".join(f"{k}={v}" for k, v in sorted(hist.items())) or "none"
    lines.append(f"failure categories: {hist_str}")
    lines.append(f"latency (s): min {lat['min']:.1f}  mean {lat['mean']:.1f}  max {lat['max']:.1f}")
    lines.append("")
    lines.append("per case")
    lines.append(f"  {'id':<4} {'fam':<3} {'appr':<5} {'att':<3} {'rep':<3} "
                 f"{'raw-sv':<6} {'raw-wgv':<7} {'cat':<16} "
                 f"{'t-P/R(final)':<12} {'e-P/R(final)':<12} lat")
    for case in run.cases:
        fs = case.final_score
        tpr = f"{fs.tasks.precision:.2f}/{fs.tasks.recall:.2f}" if fs else "-"
        epr = f"{fs.edges.precision:.2f}/{fs.edges.recall:.2f}" if fs else "-"
        lines.append(
            f"  {case.id:<4} {case.family:<3} {str(case.approved):<5} {case.attempts:<3} "
            f"{str(case.repaired):<3} {str(case.raw_schema_valid):<6} "
            f"{str(case.raw_whole_graph_valid):<7} {str(case.failure_category or ''):<16} "
            f"{tpr:<12} {epr:<12} {case.latency_s:.1f}"
        )
    return "\n".join(lines)


def _axis_dict(m: AxisMetrics) -> dict:
    return {
        "scored": m.scored,
        "exact_match": m.exact_match,
        "task": {
            "precision_mean": m.task_precision_mean,
            "recall_mean": m.task_recall_mean,
            "micro": {"tp": m.task_micro.tp, "fp": m.task_micro.fp, "fn": m.task_micro.fn},
        },
        "edge": {
            "precision_mean": m.edge_precision_mean,
            "recall_mean": m.edge_recall_mean,
            "micro": {"tp": m.edge_micro.tp, "fp": m.edge_micro.fp, "fn": m.edge_micro.fn},
        },
    }


def to_dict(run: EvalRun) -> dict:
    return {
        "meta": {
            "backend_kind": run.backend_kind,
            "model": run.model,
            "scene_hash": run.scene_hash,
            "validator_version": run.validator_version,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
        },
        "counts": run.counts(),
        "failure_histogram": run.failure_histogram(),
        "latency_stats": run.latency_stats(),
        "axes": {axis: _axis_dict(run.axis(axis)) for axis in ("raw", "final")},
        "by_family": {
            fam: {
                "n": d["n"],
                "approved": d["approved"],
                "raw_whole_graph_valid": d["raw_whole_graph_valid"],
                "final": _axis_dict(d["final"]),  # type: ignore[arg-type]
            }
            for fam, d in run.by_family().items()
        },
        "cases": [
            {
                "id": c.id,
                "family": c.family,
                "profile": c.profile,
                "command": c.command,
                "approved": c.approved,
                "attempts": c.attempts,
                "repaired": c.repaired,
                "raw_schema_valid": c.raw_schema_valid,
                "raw_whole_graph_valid": c.raw_whole_graph_valid,
                "repaired_whole_graph_valid": c.repaired_whole_graph_valid,
                "failure_category": c.failure_category,
                "latency_s": c.latency_s,
                "resolved_models": list(c.resolved_models),
                "raw_score": _score_dict(c.raw_score),
                "final_score": _score_dict(c.final_score),
            }
            for c in run.cases
        ],
    }


def _score_dict(s) -> dict | None:
    if s is None:
        return None
    return {
        "ref_index": s.ref_index,
        "exact_match": s.exact_match,
        "task": {"tp": s.tasks.tp, "fp": s.tasks.fp, "fn": s.tasks.fn,
                 "precision": s.tasks.precision, "recall": s.tasks.recall},
        "edge": {"tp": s.edges.tp, "fp": s.edges.fp, "fn": s.edges.fn,
                 "precision": s.edges.precision, "recall": s.edges.recall},
    }


def to_json(run: EvalRun, *, indent: int = 2) -> str:
    return json.dumps(to_dict(run), indent=indent, sort_keys=True)


__all__ = ["text_report", "to_dict", "to_json"]
