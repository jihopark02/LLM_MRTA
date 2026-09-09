"""Aggregate per-turn latency from interaction audit JSON (D-071).

Reads ``data/interaction_runs/*.json`` (or another directory) and reports, per
``intent_kind``, the distribution of ``total_s`` / ``llm_total_s`` /
``deterministic_s`` and the mean of each LLM call schema. Measurement only —
this reads the ``timing`` field the orchestrator already writes, it does not
call a model.

    python3 -m evaluation.latency [--runs DIR] [--mode live|cached|mock] [--json]
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

DEFAULT_RUNS = Path(__file__).resolve().parents[1] / "data" / "interaction_runs"

_FIELDS = ("total_s", "llm_total_s", "deterministic_s")


def _turn_events(runs_dir: Path, mode: str | None):
    for path in sorted(runs_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for event in payload.get("events", []):
            if event.get("event_type") != "TURN" or event.get("timing") is None:
                continue
            if mode is not None and event.get("mode") != mode:
                continue
            yield event


def collect(runs_dir: Path, mode: str | None) -> dict:
    by_kind: dict[str, list[dict]] = defaultdict(list)
    for event in _turn_events(runs_dir, mode):
        by_kind[event.get("intent_kind") or "UNKNOWN"].append(event["timing"])
    out: dict[str, dict] = {}
    for kind, timings in sorted(by_kind.items()):
        row: dict = {"n": len(timings)}
        for field in _FIELDS:
            vals = sorted(t[field] for t in timings)
            row[field] = {
                "mean": statistics.fmean(vals),
                "median": statistics.median(vals),
                "p95": vals[max(0, round(0.95 * (len(vals) - 1)))],
                "max": vals[-1],
            }
        calls: dict[str, list[float]] = defaultdict(list)
        for t in timings:
            for name, seconds in t["llm_calls"]:
                calls[name].append(seconds)
        row["llm_calls"] = {
            name: {"n": len(v), "mean": statistics.fmean(v)}
            for name, v in sorted(calls.items())
        }
        out[kind] = row
    return out


def _format(summary: dict) -> str:
    if not summary:
        return "no timed turns found"
    lines = []
    for kind, row in summary.items():
        lines.append(f"{kind}  (n={row['n']})")
        for field in _FIELDS:
            s = row[field]
            lines.append(
                f"  {field:<16} mean {s['mean']:.2f}s  median {s['median']:.2f}s  "
                f"p95 {s['p95']:.2f}s  max {s['max']:.2f}s"
            )
        if row["llm_calls"]:
            for name, c in row["llm_calls"].items():
                lines.append(f"    {name:<20} n={c['n']}  mean {c['mean']:.2f}s")
        lines.append("")
    return "\n".join(lines).rstrip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evaluation.latency")
    parser.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--mode", choices=("live", "cached", "mock"), default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if not args.runs.is_dir():
        parser.error(f"no such directory: {args.runs}")
    summary = collect(args.runs, args.mode)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(_format(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
