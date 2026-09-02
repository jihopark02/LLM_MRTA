"""Thin end-to-end integration runner (RESEARCH_CONTRACT.md §15 P6.5, D-025).

One NL command, all the way through:

    command -> generate_mission()  (RQ1: LLM graph structure + Validator)
            -> allocate()          (RQ2: platform-aware CBBA, plan-time)
            -> SimExecutor.run()   (RQ2: 2D execution)

No new algorithm — this only wires the P1-P6 modules together so the whole
pipeline can be demonstrated on a real command. If the mission is not approved,
``allocation`` and ``execution`` are None and the run stops at RQ1.

    python3 -m evaluation.integration [--mock] [--command A1 B1 ...] [--out PREFIX]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from allocation.allocate import AllocationResult, allocate
from core.mission_state import MissionState
from evaluation.annotations import Annotation, load_all
from execution.executor import ExecutionResult, SimExecutor
from llm.pipeline import GenerationResult, generate_mission
from scenarios.scene import Scene, load_scene

_SCENE = Path(__file__).resolve().parents[1] / "scenarios" / "industrial_park.yaml"
_DEFAULT_COMMANDS = ("A1", "B1", "C1")  # full / aerial-only / selective


@dataclass
class FullRun:
    id: str
    command: str
    gen: GenerationResult
    allocation: AllocationResult | None
    execution: ExecutionResult | None

    @property
    def approved(self) -> bool:
        return self.gen.approved

    @property
    def clean(self) -> bool:
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
            and not e.deadlocked
            and not e.unfinished_tasks
            and not e.capability_violations
            and not e.precedence_violations
        )


def run_full(command: str, scene: Scene, backend, *, run_id: str = "") -> FullRun:
    gen = generate_mission(command, scene, backend)
    if not gen.approved or gen.graph is None:
        return FullRun(run_id, command, gen, None, None)

    fleet = {a.agent_id: a for a in scene.fleet}
    allocation = allocate(MissionState(gen.graph, fleet), scene)
    execution = SimExecutor(MissionState(gen.graph, fleet), scene).run()
    return FullRun(run_id, command, gen, allocation, execution)


def run_commands(
    annotations: list[Annotation], scene: Scene, backend
) -> list[FullRun]:
    return [run_full(a.command, scene, backend, run_id=a.id) for a in annotations]


# -- reporting ------------------------------------------------------


def _row(r: FullRun) -> str:
    if not r.approved:
        return f"  {r.id:<4} REJECTED ({r.gen.failure_category})"
    a, e = r.allocation, r.execution
    assert a is not None and e is not None
    return (
        f"  {r.id:<4} approved  tasks {len(r.gen.graph)}/{len(r.gen.graph.edges)}e  "
        f"alloc mk {a.estimated_makespan:7.1f}  exec mk {e.makespan:7.1f}  "
        f"viol {len(a.capability_violations)+len(a.precedence_violations)}"
        f"/{len(e.capability_violations)+len(e.precedence_violations)}  "
        f"{'OK' if r.clean else 'CHECK'}"
    )


def text_report(runs: list[FullRun]) -> str:
    lines = ["end-to-end integration (NL -> generate_mission -> allocate -> SimExecutor)",
             "=" * 70]
    for r in runs:
        lines.append(_row(r))
    clean = sum(x.clean for x in runs)
    lines.append(f"\n{clean}/{len(runs)} commands ran clean through the full pipeline")
    return "\n".join(lines)


def _run_dict(r: FullRun) -> dict:
    d: dict = {
        "id": r.id,
        "command": r.command,
        "approved": r.approved,
        "clean": r.clean,
    }
    if r.gen.graph is not None:
        d["graph"] = {"tasks": len(r.gen.graph), "edges": len(r.gen.graph.edges)}
    if r.allocation is not None:
        a = r.allocation
        d["allocation"] = {
            "success": a.allocation_success,
            "unassigned": a.unassigned_tasks,
            "capability_violations": a.capability_violations,
            "precedence_violations": a.precedence_violations,
            "estimated_makespan": a.estimated_makespan,
            "uav_flight_distance": a.uav_flight_distance,
            "ugv_route_distance": a.ugv_route_distance,
            "workload": a.workload,
            "idle_agents": a.idle_agents,
            "consensus_rounds": a.consensus_rounds,
        }
    if r.execution is not None:
        e = r.execution
        d["execution"] = {
            "termination": e.termination.value,
            "makespan": e.makespan,
            "epochs": e.epochs,
            "completed": len(e.completed),
            "unfinished_tasks": e.unfinished_tasks,
            "capability_violations": e.capability_violations,
            "precedence_violations": e.precedence_violations,
            "workload": e.workload,
            "idle_agents": e.idle_agents,
        }
    return d


def to_json(runs: list[FullRun]) -> str:
    return json.dumps([_run_dict(r) for r in runs], indent=2, sort_keys=True)


# -- CLI -----------------------------------------------------------


def _mock_backend(annotations: list[Annotation]):
    from llm.backend import MockBackend
    from llm.schemas import LLMEdge, LLMTask, Step1Output, Step2Output

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
        script += [Step1Output(tasks=tasks), Step2Output(edges=edges)]
    return MockBackend(script)


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

    backend = _mock_backend(anns) if args.mock else _openai_backend(args.model)
    runs = run_commands(anns, scene, backend)
    report = text_report(runs)
    print(report)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.with_suffix(".json").write_text(to_json(runs))
        out.with_suffix(".txt").write_text(report + "\n")
        print(f"\nwrote {out.with_suffix('.json')} and {out.with_suffix('.txt')}")
    return 0 if all(r.clean for r in runs) else 1


def _openai_backend(model: str):
    from llm.backend import OpenAIBackend

    return OpenAIBackend(model=model)


if __name__ == "__main__":
    sys.exit(main())
