"""End-to-end integration runner (RESEARCH_CONTRACT.md §15 P6.5, D-025, D-026).

One NL command, all the way through — but a **fork**, not a pipe:

    command
      -> generate_mission()              (RQ1: LLM graph structure + Validator)
      -> validated graph  ─┬→ allocate()          (RQ2: plan-time CBBA analysis)
                           └→ SimExecutor.run()   (RQ2: event-driven CBBA execution)

``SimExecutor`` re-runs CBBA internally as the READY frontier changes; it does
NOT consume ``allocate``'s assignment. The two are independent analyses of the
same validated graph (estimated makespan vs actual execution, §13).

No new algorithm — this only wires the P1-P6 modules together so the whole
pipeline can be demonstrated and audited on a real command.

    python3 -m evaluation.integration [--mock] [--command A1 B1 ...] [--out PREFIX]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from allocation.allocate import AllocationResult, allocate
from core.mission_state import MissionState
from evaluation.annotations import Annotation, load_all
from evaluation.harness import GraphSnapshot, snapshot
from evaluation.metrics import GraphScore, score_graph
from execution.executor import ExecutionResult, SimExecutor, Termination
from llm.pipeline import GenerationResult, generate_mission
from scenarios.scene import Scene, load_scene
from validator.hashing import VALIDATOR_VERSION, scene_hash

_SCENE = Path(__file__).resolve().parents[1] / "scenarios" / "industrial_park.yaml"
_DEFAULT_COMMANDS = ("A1", "B1", "C1")  # full / aerial-only / selective


@dataclass
class FullRun:
    id: str
    command: str
    gen: GenerationResult
    final_snapshot: GraphSnapshot | None
    score: GraphScore | None
    allocation: AllocationResult | None
    execution: ExecutionResult | None
    resolved_models: tuple[str, ...]
    harness_error: str | None = None

    @property
    def approved(self) -> bool:
        return self.gen.approved

    @property
    def exact_match(self) -> bool:
        return self.score is not None and self.score.exact_match

    @property
    def operationally_clean(self) -> bool:
        """RQ1 approved, and RQ2 allocated + executed with no violations."""
        a, e = self.allocation, self.execution
        return bool(
            self.approved
            and a is not None
            and a.allocation_success
            and not a.unassigned_tasks
            and not a.capability_violations
            and not a.precedence_violations
            and e is not None
            and e.termination is Termination.COMPLETED
            and not e.unfinished_tasks
            and not e.capability_violations
            and not e.precedence_violations
        )

    @property
    def demo_pass(self) -> bool:
        """The graph is the RIGHT one for the command AND it runs cleanly."""
        return self.operationally_clean and self.exact_match


def run_full(ann: Annotation, scene: Scene, backend, *, on_error: str = "record") -> FullRun:
    before = len(getattr(backend, "resolved_models", ()))
    try:
        gen = generate_mission(ann.command, scene, backend)
    except Exception as exc:  # noqa: BLE001 - one bad command must not kill the run
        if on_error == "raise":
            raise
        resolved = tuple(getattr(backend, "resolved_models", ())[before:])
        return FullRun(ann.id, ann.command, _empty_gen(ann.command), None, None,
                       None, None, resolved, harness_error=f"{type(exc).__name__}: {exc}")
    resolved = tuple(getattr(backend, "resolved_models", ())[before:])

    final_snapshot = snapshot(scene, gen.candidate, gen.validation)
    score = score_graph(gen.candidate, ann.allowed_graphs) if gen.candidate is not None else None
    if not gen.approved or gen.graph is None:
        return FullRun(ann.id, ann.command, gen, final_snapshot, score, None, None, resolved)

    fleet = {a.agent_id: a for a in scene.fleet}
    allocation = allocate(MissionState(gen.graph, fleet), scene)
    execution = SimExecutor(MissionState(gen.graph, fleet), scene).run()
    return FullRun(ann.id, ann.command, gen, final_snapshot, score, allocation, execution, resolved)


def _empty_gen(command: str) -> GenerationResult:
    return GenerationResult(
        command=command, approved=False, attempts=0, repaired=False,
        raw_schema_valid=False, raw_whole_graph_valid=False, failure_category=None,
    )


def run_commands(anns: list[Annotation], scene: Scene, backend, *, on_error: str = "record"):
    return [run_full(a, scene, backend, on_error=on_error) for a in anns]


# -- reporting ------------------------------------------------------


def _row(r: FullRun) -> str:
    if r.harness_error:
        return f"  {r.id:<4} HARNESS_ERROR ({r.harness_error})"
    if not r.approved:
        return f"  {r.id:<4} REJECTED ({r.gen.failure_category})"
    a, e = r.allocation, r.execution
    assert a is not None and e is not None
    verdict = "PASS" if r.demo_pass else ("op-only" if r.operationally_clean else "CHECK")
    return (
        f"  {r.id:<4} approved  exact={str(r.exact_match):<5}  "
        f"tasks {len(r.gen.graph)}/{len(r.gen.graph.edges)}e  "
        f"alloc mk {a.estimated_makespan:7.1f}  exec mk {e.makespan:7.1f}  "
        f"viol {len(a.capability_violations) + len(a.precedence_violations)}"
        f"/{len(e.capability_violations) + len(e.precedence_violations)}  {verdict}"
    )


def text_report(runs: list[FullRun]) -> str:
    lines = [
        "end-to-end integration (NL -> generate_mission;"
        " validated graph -> allocate | SimExecutor)",
        "=" * 70,
    ]
    lines += [_row(r) for r in runs]
    lines.append(
        f"\n{sum(r.demo_pass for r in runs)}/{len(runs)} demo_pass "
        f"(exact-match graph + clean plan + clean execution)"
    )
    return "\n".join(lines)


def _run_dict(r: FullRun) -> dict:
    d: dict = {
        "id": r.id,
        "command": r.command,
        "approved": r.approved,
        "exact_match": r.exact_match,
        "operationally_clean": r.operationally_clean,
        "demo_pass": r.demo_pass,
        "harness_error": r.harness_error,
        "resolved_models": list(r.resolved_models),
    }
    if r.final_snapshot is not None:
        s = r.final_snapshot
        d["generation"] = {
            "tasks": s.tasks,
            "edges": s.edges,
            "graph_hash": s.graph_hash,
            "accepted": s.accepted,
            "error_codes": s.error_codes,
            "repaired": r.gen.repaired,
        }
        if r.score is not None:
            d["generation"]["score"] = {
                "ref_index": r.score.ref_index,
                "task": {"tp": r.score.tasks.tp, "fp": r.score.tasks.fp, "fn": r.score.tasks.fn},
                "edge": {"tp": r.score.edges.tp, "fp": r.score.edges.fp, "fn": r.score.edges.fn},
            }
    if r.allocation is not None:
        a = r.allocation
        d["plan_analysis"] = {
            "assignments": a.assignments,  # task_id -> agent_id
            "estimated_makespan": a.estimated_makespan,
            "unassigned": a.unassigned_tasks,
            "capability_violations": a.capability_violations,
            "precedence_violations": a.precedence_violations,
            "uav_flight_distance": a.uav_flight_distance,
            "ugv_route_distance": a.ugv_route_distance,
            "workload": a.workload,
            "consensus_rounds": a.consensus_rounds,
        }
    if r.execution is not None:
        e = r.execution
        d["execution"] = {
            "termination": e.termination.value,
            "assignments": dict(e.assignments),  # task_id -> agent_id
            "winning_bids": e.winning_bids,
            "makespan": e.makespan,
            "epochs": e.epochs,
            "completed": len(e.completed),
            "unfinished_tasks": e.unfinished_tasks,
            "capability_violations": e.capability_violations,
            "precedence_violations": e.precedence_violations,
            "workload": e.workload,
        }
    return d


def to_dict(runs: list[FullRun], scene: Scene, *, requested_model: str | None,
            started_at: str, finished_at: str) -> dict:
    return {
        "meta": {
            "scene_hash": scene_hash(scene),
            "validator_version": VALIDATOR_VERSION,
            "requested_model": requested_model,
            "started_at": started_at,
            "finished_at": finished_at,
            "structure": "fork: validated graph -> allocate (plan-time) AND "
                         "SimExecutor (event-driven); allocate result is not fed to the executor",
        },
        "cases": [_run_dict(r) for r in runs],
    }


def to_json(runs, scene, **meta) -> str:
    return json.dumps(to_dict(runs, scene, **meta), indent=2, sort_keys=True)


# -- CLI -----------------------------------------------------------


def _mock_backend(anns: list[Annotation]):
    from llm.backend import MockBackend
    from llm.schemas import LLMEdge, LLMTask, Step1Output, Step2Output

    script: list = []
    for ann in anns:
        g = ann.allowed_graphs[0]
        tasks = [
            LLMTask(task_type=tt.value, target=target)
            for tt, target in sorted(g.tasks, key=lambda k: (k[0].value, k[1]))
        ]
        edges = [
            LLMEdge(predecessor=f"{p[0].value}:{p[1]}", successor=f"{s[0].value}:{s[1]}")
            for p, s in g.edges
        ]
        script += [Step1Output(tasks=tasks), Step2Output(edges=edges)]
    return MockBackend(script)


def _openai_backend(model: str):
    from llm.backend import OpenAIBackend

    return OpenAIBackend(model=model)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evaluation.integration")
    parser.add_argument("--mock", action="store_true", help="perfect MockBackend, no network")
    parser.add_argument("--model", default="gpt-5-mini")
    parser.add_argument("--command", nargs="+", default=list(_DEFAULT_COMMANDS),
                        help="annotation ids to run (default: A1 B1 C1)")
    parser.add_argument("--out", help="path prefix for <out>.json / <out>.txt")
    args = parser.parse_args(argv)

    scene = load_scene(_SCENE)
    by_id = {a.id: a for a in load_all(scene)}
    try:
        anns = [by_id[c] for c in args.command]
    except KeyError as e:
        parser.error(f"unknown command id {e}; choose from {sorted(by_id)}")

    requested_model = None if args.mock else args.model
    backend = _mock_backend(anns) if args.mock else _openai_backend(args.model)

    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    runs = run_commands(anns, scene, backend)
    finished = datetime.now(timezone.utc).isoformat(timespec="seconds")

    report = text_report(runs)
    print(report)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.with_suffix(".json").write_text(
            to_json(runs, scene, requested_model=requested_model,
                    started_at=started, finished_at=finished)
        )
        out.with_suffix(".txt").write_text(report + "\n")
        print(f"\nwrote {out.with_suffix('.json')} and {out.with_suffix('.txt')}")
    return 0 if all(r.demo_pass for r in runs) else 1


if __name__ == "__main__":
    sys.exit(main())
