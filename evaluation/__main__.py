"""Run the P6 evaluation (RESEARCH_CONTRACT.md §12, §14, D-021).

    python -m evaluation                      # real run: OpenAIBackend(gpt-5-mini)
    python -m evaluation --mock               # smoke run with a perfect MockBackend
    python -m evaluation --out results/p6     # also write <out>.json and <out>.txt

The real run needs the 'llm' extra (``pip install -e '.[llm]'``) and
``OPENAI_API_KEY`` in the environment or repo-root ``.env``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from evaluation.annotations import load_all
from evaluation.harness import run_all
from evaluation.report import text_report, to_json
from scenarios.scene import load_scene

_SCENE = Path(__file__).resolve().parents[1] / "scenarios" / "industrial_park.yaml"


def _mock_backend(scene, annotations):
    from llm.backend import MockBackend
    from llm.schemas import LLMEdge, LLMTask, Step1Output, Step2Output

    script: list = []
    for ann in annotations:
        g = ann.allowed_graphs[0]
        tasks = [
            LLMTask(
                task_type=tt.value,
                target=target,
                priority=scene.incidents[target].priority if target in scene.incidents else 5,
            )
            for tt, target in sorted(g.tasks, key=lambda k: (k[0].value, k[1]))
        ]
        edges = [
            LLMEdge(predecessor=f"{p[0].value}:{p[1]}", successor=f"{s[0].value}:{s[1]}")
            for p, s in g.edges
        ]
        script += [Step1Output(tasks=tasks), Step2Output(edges=edges)]
    return MockBackend(script)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evaluation")
    parser.add_argument("--mock", action="store_true", help="perfect MockBackend, no network")
    parser.add_argument("--model", default="gpt-5-mini", help="OpenAI model (real run)")
    parser.add_argument("--out", help="path prefix for <out>.json and <out>.txt")
    args = parser.parse_args(argv)

    scene = load_scene(_SCENE)
    annotations = load_all(scene)

    if args.mock:
        backend = _mock_backend(scene, annotations)
    else:
        from llm.backend import OpenAIBackend

        backend = OpenAIBackend(model=args.model)

    run = run_all(scene, backend, annotations=annotations)
    report = text_report(run)
    print(report)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.with_suffix(".json").write_text(to_json(run))
        out.with_suffix(".txt").write_text(report + "\n")
        print(f"\nwrote {out.with_suffix('.json')} and {out.with_suffix('.txt')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
