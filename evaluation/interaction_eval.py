"""CLI for P8.4 interaction evaluation.

    python3 -m evaluation.interaction_eval --grounder-only
    python3 -m evaluation.interaction_eval --cached --out data/eval_results/p8_4_cached
    python3 -m evaluation.interaction_eval --out data/eval_results/p8_4_gpt-5-mini
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from evaluation.interaction_annotations import load_all_dialogues
from evaluation.interaction_harness import run_interaction_eval
from evaluation.interaction_report import text_report, to_json
from scenarios.scene import load_scene

_ROOT = Path(__file__).resolve().parents[1]
_SCENE = _ROOT / "scenarios" / "industrial_park.yaml"


def _write(run, prefix: str) -> list[Path]:
    path = Path(prefix)
    path.parent.mkdir(parents=True, exist_ok=True)
    json_path = path.with_suffix(".json")
    text_path = path.with_suffix(".txt")
    json_path.write_text(to_json(run) + "\n", encoding="utf-8")
    text_path.write_text(text_report(run) + "\n", encoding="utf-8")
    return [json_path, text_path]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evaluation.interaction_eval")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--grounder-only", action="store_true", help="gold intent/slots, no network"
    )
    mode.add_argument("--cached", action="store_true", help="exact cached LLM replay only")
    parser.add_argument("--model", default="gpt-5-mini")
    parser.add_argument("--cache-dir", default=str(_ROOT / "data" / "llm_cache"))
    parser.add_argument("--out", help="path prefix for .json and .txt")
    args = parser.parse_args(argv)

    scene = load_scene(_SCENE)
    dialogues = load_all_dialogues(scene)
    if args.grounder_only:
        run = run_interaction_eval(scene, dialogues, track="grounder-only")
    else:
        if args.cached:
            from llm.cache import CachedBackend

            def factory(_dialogue):
                return CachedBackend(args.model, args.cache_dir)
        else:
            from llm.backend import OpenAIBackend
            from llm.cache import RecordingBackend

            def factory(_dialogue):
                return RecordingBackend(OpenAIBackend(model=args.model), args.cache_dir)
        run = run_interaction_eval(
            scene,
            dialogues,
            track="end-to-end",
            backend_factory=factory,
            model=args.model,
        )

    report = text_report(run)
    print(report)
    if args.out:
        written = _write(run, args.out)
        print("\nwrote " + ", ".join(str(path) for path in written))
    return 0


if __name__ == "__main__":
    sys.exit(main())
