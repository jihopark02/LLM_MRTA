"""A/B: single-call vs two-stage graph generation (RESEARCH_CONTRACT.md §12).

Runs a command set through ``generate_mission`` both ways and reports per-mode
graph quality, the D-074 non-inferiority gates, and paired latency. Measurement
only — adoption of single-call as the ``generate_mission`` default is a separate
contract decision made from these numbers.

    --set p6          fixed 9-command P6 set (industrial_park) — baseline, no gate
    --set linguistic  D-074 Stress-L, 19 hard English commands (industrial_park)
    --set scale        D-074 Stress-S, 15 commands (stress_grid, 15 zone / 4 fire)

    python3 -m evaluation.graph_gen_ablation --set linguistic          # live
    python3 -m evaluation.graph_gen_ablation --set scale --mock        # smoke
    python3 -m evaluation.graph_gen_ablation --set linguistic --out results/d074_L
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from core.enums import TaskType
from evaluation.annotations import RefGraph, load_all
from evaluation.metrics import score_graph
from evaluation.stress_annotations import SET_SCENE, load_stress_set
from llm.backend import TimedBackend
from llm.pipeline import generate_mission
from scenarios.scene import Scene, load_scene
from validator.candidate import MissionCandidate
from validator.hashing import VALIDATOR_VERSION, scene_hash

_SCENARIOS = Path(__file__).resolve().parents[1] / "scenarios"
_MODES = ("two-stage", "single-call")
_SETS = ("p6", "linguistic", "scale")


@dataclass(frozen=True, slots=True)
class EvalCase:
    """The set-agnostic case the harness runs (P6 Annotation or D-074 StressCase)."""

    id: str
    command: str
    expect: str                         # approve | reject | safety-invariant
    adoption: str                       # gated | diagnostic
    allowed_graphs: tuple[RefGraph, ...]
    reject_category: str | None = None
    mock_graph: dict | None = None


def _p6_cases(scene: Scene) -> list[EvalCase]:
    return [
        EvalCase(a.id, a.command, "approve", "gated", a.allowed_graphs)
        for a in load_all(scene)
    ]


def _stress_cases(set_name: str, scene: Scene) -> list[EvalCase]:
    return [
        EvalCase(
            c.id, c.command, c.expect, c.adoption, c.allowed_graphs,
            c.reject_category, c.mock_graph,
        )
        for c in load_stress_set(set_name, scene)
    ]


def load_cases(set_name: str) -> tuple[Scene, list[EvalCase]]:
    if set_name == "p6":
        scene = load_scene(_SCENARIOS / "industrial_park.yaml")
        return scene, _p6_cases(scene)
    scene = load_scene(_SCENARIOS / SET_SCENE[set_name])
    return scene, _stress_cases(set_name, scene)


# -- per-case run --------------------------------------------------------


@dataclass
class CaseAB:
    id: str
    expect: str
    adoption: str
    approved: bool
    first_pass_valid: bool
    repaired: bool
    exact_match: bool | None            # None for reject cases
    reject_correct: bool | None         # None unless expect == reject
    safety_outcome: str | None          # rejected | restored | unsafe-accept (safety cases)
    safety_invalid_accept: bool | None
    latency_s: float
    llm_calls: int
    failure_category: str | None
    harness_error: str | None

    @property
    def gated(self) -> bool:
        return self.adoption == "gated"


def _bare_suppression(candidate: MissionCandidate) -> bool:
    """A GROUND_SUPPRESSION task with no GROUND_INSPECTION predecessor edge for
    the same incident — the workflow-safety violation the Validator must catch."""
    edges = {(e.predecessor, e.successor) for e in candidate.edges}
    for task in candidate.tasks:
        if task.task_type is not TaskType.GROUND_SUPPRESSION:
            continue
        pred = (TaskType.GROUND_INSPECTION, task.target)
        if (pred, (TaskType.GROUND_SUPPRESSION, task.target)) not in edges:
            return True
    return False


def _run_case(case: EvalCase, scene: Scene, backend: TimedBackend, single_call: bool) -> CaseAB:
    mark = len(backend.calls)
    t0 = time.perf_counter()
    try:
        gen = generate_mission(case.command, scene, backend, single_call=single_call)
    except Exception as exc:  # noqa: BLE001 - one bad case must not sink the run
        return CaseAB(
            case.id, case.expect, case.adoption, False, False, False, None, None,
            None, None, time.perf_counter() - t0, len(backend.calls) - mark, None,
            f"{type(exc).__name__}: {exc}",
        )
    latency = time.perf_counter() - t0
    calls = len(backend.calls) - mark

    exact = reject_correct = safety_outcome = safety_invalid = None
    if case.expect == "reject":
        reject_correct = (not gen.approved) and gen.failure_category == case.reject_category
    elif case.expect == "safety-invariant":
        if not gen.approved:
            safety_outcome, safety_invalid = "rejected", False
        elif gen.candidate is not None and _bare_suppression(gen.candidate):
            safety_outcome, safety_invalid = "unsafe-accept", True
        else:
            safety_outcome, safety_invalid = "restored", False
    if case.allowed_graphs and gen.candidate is not None:
        exact = bool(score_graph(gen.candidate, case.allowed_graphs).exact_match)

    return CaseAB(
        case.id, case.expect, case.adoption, gen.approved, gen.raw_whole_graph_valid,
        gen.repaired, exact, reject_correct, safety_outcome, safety_invalid,
        latency, calls, gen.failure_category, None,
    )


# -- mock scripting -----------------------------------------------------


def _tasks_edges(graph: RefGraph):
    from llm.schemas import LLMEdge, LLMTask

    tasks = [
        LLMTask(task_type=tt.value, target=tgt)
        for tt, tgt in sorted(graph.tasks, key=lambda k: (k[0].value, k[1]))
    ]
    edges = [
        LLMEdge(predecessor=f"{p[0].value}:{p[1]}", successor=f"{s[0].value}:{s[1]}")
        for p, s in sorted(graph.edges, key=lambda e: (e[0][1], e[1][1]))
    ]
    return tasks, edges


def _raw_tasks_edges(raw: dict):
    from llm.schemas import LLMEdge, LLMTask

    tasks = [LLMTask(task_type=t["task_type"], target=t["target"]) for t in raw["tasks"]]
    edges = [LLMEdge(predecessor=e[0], successor=e[1]) for e in raw.get("edges", [])]
    return tasks, edges


def _mock_script(case: EvalCase, mode: str) -> list:
    """The scripted responses a MockBackend serves for one case, one mode.

    approve/diagnostic: the first allowed graph.
    reject: the deliberately-invalid mock_graph, then the same graph as the
    (still-failing) repair.
    safety-invariant: the bare-suppression mock_graph, then the prerequisite-
    restored allowed graph as the repair.
    """
    from llm.schemas import GraphOutput, Step1Output, Step2Output

    if case.expect == "approve":
        first_t, first_e = _tasks_edges(case.allowed_graphs[0])
        repair = None
    elif case.expect == "reject":
        first_t, first_e = _raw_tasks_edges(case.mock_graph)
        repair = (first_t, [])
    else:  # safety-invariant
        first_t, first_e = _raw_tasks_edges(case.mock_graph)
        rt, re = _tasks_edges(case.allowed_graphs[0])
        repair = (rt, re)

    script: list = []
    if mode == "single-call":
        script.append(GraphOutput(tasks=first_t, edges=first_e))
    else:
        script += [Step1Output(tasks=first_t), Step2Output(edges=first_e)]
    if repair is not None:
        from llm.schemas import RepairOutput

        script.append(RepairOutput(tasks=repair[0], edges=repair[1]))
    return script


def _mock_backend_for(cases: list[EvalCase]):
    def build(mode: str):
        from llm.backend import MockBackend

        script: list = []
        for case in cases:
            script += _mock_script(case, mode)
        return MockBackend(script)

    return build


# -- run + aggregate ---------------------------------------------------


@dataclass
class ModeRun:
    mode: str
    cases: list[CaseAB]
    resolved_models: tuple[str, ...] = field(default_factory=tuple)

    def _gated_approveish(self) -> list[CaseAB]:
        return [
            c for c in self.cases
            if c.harness_error is None and c.gated and c.expect in {"approve", "safety-invariant"}
        ]

    def summary(self) -> dict:
        ok = [c for c in self.cases if c.harness_error is None]
        ga = self._gated_approveish()
        rejects = [c for c in ok if c.expect == "reject"]
        safety = [c for c in ok if c.expect == "safety-invariant"]
        return {
            "n": len(self.cases),
            "harness_errors": len(self.cases) - len(ok),
            "gated_denominator": len(ga),
            "exact_match": sum(bool(c.exact_match) for c in ga),
            "first_pass_valid": sum(c.first_pass_valid for c in ga),
            "repaired": sum(c.repaired for c in ok),
            "reject_cases": len(rejects),
            "reject_correct": sum(bool(c.reject_correct) for c in rejects),
            "safety_cases": len(safety),
            "safety_invalid_accept": sum(bool(c.safety_invalid_accept) for c in safety),
            "llm_calls_total": sum(c.llm_calls for c in ok),
            "latency_s_mean": statistics.fmean([c.latency_s for c in ok]) if ok else 0.0,
            "latency_s_median": statistics.median([c.latency_s for c in ok]) if ok else 0.0,
        }


def run(scene: Scene, backend_for, cases: list[EvalCase]) -> list[ModeRun]:
    runs = []
    for mode in _MODES:
        timed = TimedBackend(backend_for(mode))
        single = mode == "single-call"
        results = [_run_case(c, scene, timed, single) for c in cases]
        resolved = tuple(dict.fromkeys(getattr(timed, "resolved_models", ())))
        runs.append(ModeRun(mode, results, resolved))
    return runs


def paired_latency(runs: list[ModeRun]) -> dict:
    two = {c.id: c for c in _by_mode(runs, "two-stage").cases}
    one = {c.id: c for c in _by_mode(runs, "single-call").cases}
    pairs = []
    for cid in sorted(two):
        t2, t1 = two[cid], one[cid]
        if t2.harness_error or t1.harness_error or t2.latency_s <= 0:
            continue
        pairs.append({
            "id": cid,
            "two_stage_s": t2.latency_s,
            "single_call_s": t1.latency_s,
            "reduction": (t2.latency_s - t1.latency_s) / t2.latency_s,
        })
    reductions = [p["reduction"] for p in pairs]
    faster = sum(p["single_call_s"] < p["two_stage_s"] for p in pairs)
    return {
        "pairs": pairs,
        "n": len(pairs),
        "median_reduction": statistics.median(reductions) if reductions else 0.0,
        "mean_reduction": statistics.fmean(reductions) if reductions else 0.0,
        "single_faster_fraction": (faster / len(pairs)) if pairs else 0.0,
    }


def _by_mode(runs: list[ModeRun], mode: str) -> ModeRun:
    return next(r for r in runs if r.mode == mode)


def gates(runs: list[ModeRun], *, gate_enabled: bool) -> dict:
    """The D-074 non-inferiority gates. ``gate_enabled`` is False for --set p6."""
    two, one = _by_mode(runs, "two-stage").summary(), _by_mode(runs, "single-call").summary()
    pl = paired_latency(runs)
    n_gated = one["gated_denominator"]

    exact = one["exact_match"] >= two["exact_match"] - 1 and (
        n_gated == 0 or one["exact_match"] >= 0.85 * n_gated
    )
    first_pass = one["first_pass_valid"] >= two["first_pass_valid"] - 1 and (
        n_gated == 0 or one["first_pass_valid"] >= 0.85 * n_gated
    )
    reject_ok = (
        one["reject_correct"] == one["reject_cases"]
        and one["reject_correct"] >= two["reject_correct"]
    )
    safety_ok = one["safety_invalid_accept"] == 0
    latency_ok = pl["median_reduction"] >= 0.25 and pl["single_faster_fraction"] >= 0.80

    checks = {
        "exact_match": exact,
        "first_pass_valid": first_pass,
        "explicit_reject": reject_ok,
        "safety_invalid_acceptance": safety_ok,
        "paired_latency": latency_ok,
    }
    return {
        "enabled": gate_enabled,
        "checks": checks,
        "all_pass": gate_enabled and all(checks.values()),
        "detail": {
            "two_stage": two, "single_call": one,
            "gated_denominator": n_gated,
            "latency": {k: pl[k] for k in
                        ("n", "median_reduction", "mean_reduction", "single_faster_fraction")},
        },
    }


# -- output -----------------------------------------------------------


def to_json(set_name: str, scene: Scene, runs: list[ModeRun]) -> str:
    payload = {
        "d074_graph_gen_ablation": True,
        "set": set_name,
        "scene_hash": scene_hash(scene),
        "validator_version": VALIDATOR_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "gates": gates(runs, gate_enabled=set_name != "p6"),
        "paired_latency": paired_latency(runs),
        "modes": {
            r.mode: {
                "summary": r.summary(),
                "resolved_models": list(r.resolved_models),
                "cases": [asdict(c) for c in r.cases],
            }
            for r in runs
        },
    }
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)


def text_report(set_name: str, runs: list[ModeRun]) -> str:
    lines = [f"single-call vs two-stage graph generation — set: {set_name} (D-074)", ""]
    for r in runs:
        s = r.summary()
        lines.append(f"[{r.mode}]  n={s['n']}  harness_errors={s['harness_errors']}")
        lines.append(
            f"  exact-match {s['exact_match']}/{s['gated_denominator']}   "
            f"first-pass valid {s['first_pass_valid']}/{s['gated_denominator']}   "
            f"repaired {s['repaired']}"
        )
        lines.append(
            f"  reject correct {s['reject_correct']}/{s['reject_cases']}   "
            f"safety-invalid accept {s['safety_invalid_accept']}/{s['safety_cases']}"
        )
        lines.append(
            f"  latency mean {s['latency_s_mean']:.2f}s  median {s['latency_s_median']:.2f}s   "
            f"LLM calls {s['llm_calls_total']}"
        )
        lines.append("")
    g = gates(runs, gate_enabled=set_name != "p6")
    pl = g["detail"]["latency"]
    lines.append(f"paired latency: median reduction {pl['median_reduction']:.0%}  "
                 f"single faster {pl['single_faster_fraction']:.0%}  (n={pl['n']})")
    if g["enabled"]:
        lines.append("D-074 gates:")
        for name, ok in g["checks"].items():
            lines.append(f"  [{'PASS' if ok else 'FAIL'}] {name}")
        lines.append(f"  => {'ALL PASS' if g['all_pass'] else 'NOT ALL PASS'}")
    else:
        lines.append("(--set p6: baseline only, gates not evaluated)")
    return "\n".join(lines).rstrip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evaluation.graph_gen_ablation")
    parser.add_argument("--set", choices=_SETS, default="p6")
    parser.add_argument("--mock", action="store_true", help="perfect MockBackend, no network")
    parser.add_argument("--model", default="gpt-5-mini", help="OpenAI model (real run)")
    parser.add_argument("--out", help="path prefix for <out>.json / <out>.txt")
    args = parser.parse_args(argv)

    scene, cases = load_cases(args.set)

    if args.mock:
        backend_for = _mock_backend_for(cases)
    else:
        from llm.backend import OpenAIBackend

        def backend_for(_mode):
            return OpenAIBackend(model=args.model)

    runs = run(scene, backend_for, cases)
    report = text_report(args.set, runs)
    print(report)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.with_suffix(".json").write_text(to_json(args.set, scene, runs), encoding="utf-8")
        out.with_suffix(".txt").write_text(report + "\n", encoding="utf-8")
        print(f"\nwrote {out.with_suffix('.json')}, {out.with_suffix('.txt')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
