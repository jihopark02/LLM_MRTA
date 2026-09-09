"""A/B: single-call vs two-stage graph generation (RESEARCH_CONTRACT.md §12, D-072).

Runs the fixed P6 evaluation commands through ``generate_mission`` both ways and
reports, per mode: first-pass validator rate / repair rate / graph exact-match /
mean latency / mean LLM call count. Measurement only — this does not decide
anything. Adoption of single-call is a contract revision made from these numbers
(D-072); until then both paths stay in the code.

    python3 -m evaluation.graph_gen_ablation            # real: OpenAIBackend(gpt-5-mini)
    python3 -m evaluation.graph_gen_ablation --mock     # perfect MockBackend, no network
    python3 -m evaluation.graph_gen_ablation --out results/d072
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from evaluation.annotations import Annotation, load_all
from evaluation.metrics import score_graph
from llm.backend import TimedBackend
from llm.pipeline import generate_mission
from scenarios.scene import Scene, load_scene
from validator.hashing import VALIDATOR_VERSION, scene_hash

_SCENE = Path(__file__).resolve().parents[1] / "scenarios" / "industrial_park.yaml"
_MODES = ("two-stage", "single-call")


@dataclass
class CaseAB:
    id: str
    command: str
    approved: bool
    first_pass_valid: bool          # raw candidate passed the whole-graph Validator
    repaired: bool
    exact_match: bool               # final candidate == an allowed reference graph
    latency_s: float
    llm_calls: int
    call_schemas: list[str]
    failure_category: str | None
    harness_error: str | None


@dataclass
class ModeRun:
    mode: str
    cases: list[CaseAB]
    resolved_models: tuple[str, ...] = ()

    def summary(self) -> dict:
        n = len(self.cases)
        ok = [c for c in self.cases if c.harness_error is None]
        lat = [c.latency_s for c in ok]
        calls = [c.llm_calls for c in ok]
        return {
            "n": n,
            "harness_errors": n - len(ok),
            "approved": sum(c.approved for c in ok),
            "first_pass_valid": sum(c.first_pass_valid for c in ok),
            "repaired": sum(c.repaired for c in ok),
            "exact_match": sum(c.exact_match for c in ok),
            "latency_s_mean": (sum(lat) / len(lat)) if lat else 0.0,
            "llm_calls_mean": (sum(calls) / len(calls)) if calls else 0.0,
            "llm_calls_total": sum(calls),
        }


def _run_case(ann: Annotation, scene: Scene, backend: TimedBackend, single_call: bool) -> CaseAB:
    mark = len(backend.calls)
    t0 = time.perf_counter()
    try:
        gen = generate_mission(ann.command, scene, backend, single_call=single_call)
    except Exception as exc:  # noqa: BLE001 - one bad case must not sink the run
        return CaseAB(
            id=ann.id, command=ann.command, approved=False, first_pass_valid=False,
            repaired=False, exact_match=False, latency_s=time.perf_counter() - t0,
            llm_calls=len(backend.calls) - mark,
            call_schemas=[s for s, _ in backend.calls[mark:]],
            failure_category=None, harness_error=f"{type(exc).__name__}: {exc}",
        )
    exact = bool(
        gen.candidate is not None
        and score_graph(gen.candidate, ann.allowed_graphs).exact_match
    )
    return CaseAB(
        id=ann.id, command=ann.command, approved=gen.approved,
        first_pass_valid=gen.raw_whole_graph_valid, repaired=gen.repaired,
        exact_match=exact, latency_s=time.perf_counter() - t0,
        llm_calls=len(backend.calls) - mark,
        call_schemas=[s for s, _ in backend.calls[mark:]],
        failure_category=gen.failure_category, harness_error=None,
    )


def run(scene: Scene, backend_for, annotations: list[Annotation]) -> list[ModeRun]:
    """``backend_for(mode)`` returns a fresh backend for that mode's whole pass."""
    runs = []
    for mode in _MODES:
        timed = TimedBackend(backend_for(mode))
        single = mode == "single-call"
        cases = [_run_case(a, scene, timed, single) for a in annotations]
        resolved = tuple(dict.fromkeys(getattr(timed, "resolved_models", ())))
        runs.append(ModeRun(mode, cases, resolved))
    return runs


def _mock_backend_for(annotations):
    from llm.schemas import GraphOutput, LLMEdge, LLMTask, Step1Output, Step2Output

    def build(mode: str):
        from llm.backend import MockBackend

        script: list = []
        for ann in annotations:
            g = ann.allowed_graphs[0]
            tasks = [
                LLMTask(task_type=tt.value, target=target)
                for tt, target in sorted(g.tasks, key=lambda k: (k[0].value, k[1]))
            ]
            edges = [
                LLMEdge(predecessor=f"{p[0].value}:{p[1]}", successor=f"{s[0].value}:{s[1]}")
                for p, s in g.edges
            ]
            if mode == "single-call":
                script.append(GraphOutput(tasks=tasks, edges=edges))
            else:
                script += [Step1Output(tasks=tasks), Step2Output(edges=edges)]
        return MockBackend(script)

    return build


def to_json(scene: Scene, runs: list[ModeRun]) -> str:
    payload = {
        "d072_graph_gen_ablation": True,
        "scene_hash": scene_hash(scene),
        "validator_version": VALIDATOR_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
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


def text_report(runs: list[ModeRun]) -> str:
    lines = ["single-call vs two-stage graph generation (D-072)", ""]
    for r in runs:
        s = r.summary()
        lines.append(f"[{r.mode}]  n={s['n']}  harness_errors={s['harness_errors']}")
        lines.append(
            f"  approved {s['approved']}/{s['n']}   "
            f"first-pass valid {s['first_pass_valid']}/{s['n']}   "
            f"repaired {s['repaired']}/{s['n']}   "
            f"exact-match {s['exact_match']}/{s['n']}"
        )
        lines.append(
            f"  latency mean {s['latency_s_mean']:.2f}s   "
            f"LLM calls mean {s['llm_calls_mean']:.2f}   total {s['llm_calls_total']}"
        )
        lines.append("")
    return "\n".join(lines).rstrip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evaluation.graph_gen_ablation")
    parser.add_argument("--mock", action="store_true", help="perfect MockBackend, no network")
    parser.add_argument("--model", default="gpt-5-mini", help="OpenAI model (real run)")
    parser.add_argument("--out", help="path prefix for <out>.json / <out>.txt")
    args = parser.parse_args(argv)

    scene = load_scene(_SCENE)
    annotations = load_all(scene)

    if args.mock:
        backend_for = _mock_backend_for(annotations)
    else:
        from llm.backend import OpenAIBackend

        def backend_for(_mode):
            return OpenAIBackend(model=args.model)

    runs = run(scene, backend_for, annotations)
    report = text_report(runs)
    print(report)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.with_suffix(".json").write_text(to_json(scene, runs), encoding="utf-8")
        out.with_suffix(".txt").write_text(report + "\n", encoding="utf-8")
        print(f"\nwrote {out.with_suffix('.json')}, {out.with_suffix('.txt')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
