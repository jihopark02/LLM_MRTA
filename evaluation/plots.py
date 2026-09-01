"""P6 result figures (RESEARCH_CONTRACT.md §15: "결과 시각화").

Consumes an ``EvalRun`` (or the dict from ``evaluation.report.to_dict``) and
writes one multi-panel figure:

  1. outcome counts, X/9 (ordinal blue ramp, direct-labelled)
  2. task / edge precision & recall by family, final candidate (blue = precision,
     orange = recall)
  3. end-to-end latency per case, coloured by family

Small-sample data — every panel is labelled with raw counts, no bare
percentages. matplotlib only (``pip install -e '.[viz]'``); Agg backend, no
display needed.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from evaluation.harness import EvalRun  # noqa: E402
from evaluation.report import to_dict  # noqa: E402

# Validated categorical slots (dataviz skill reference palette, light mode).
_BLUE = "#2a78d6"
_ORANGE = "#eb6834"
_FAMILY_HUE = {"A": "#2a78d6", "B": "#eb6834", "C": "#1baf7a"}
_INK = "#0b0b0b"
_MUTED = "#52514e"
_GRID = "#e6e5e2"


def _style_axes(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(_MUTED)
    ax.tick_params(colors=_MUTED, labelcolor=_INK)


def _panel_outcomes(ax, d: dict) -> None:
    c = d["counts"]
    rep = d["repair"]
    n = c["n"]
    stages = [
        ("schema-valid", c["schema_valid"]),
        ("raw graph-valid", c["raw_whole_graph_valid"]),
        ("first-pass approved", rep["first_pass_approved"]),
        ("repair attempted", rep["attempted"]),
        ("approved", c["approved"]),
    ]
    labels = [s for s, _ in stages][::-1]
    values = [v for _, v in stages][::-1]
    y = range(len(labels))
    ax.barh(list(y), values, height=0.6, color=_BLUE)
    ax.set_xlim(0, n)
    ax.set_yticks(list(y), labels)
    ax.set_xlabel(f"cases (of {n})", color=_MUTED)
    ax.set_title("Pipeline outcomes", color=_INK, loc="left", fontweight="bold")
    for yi, v in zip(y, values, strict=True):
        ax.text(v + 0.15 if v < n else v - 0.15, yi, f"{v}/{n}",
                va="center", ha="left" if v < n else "right", color=_INK, fontsize=9)
    ax.xaxis.grid(True, color=_GRID, lw=0.8)
    ax.set_axisbelow(True)
    _style_axes(ax)


def _panel_pr(ax, d: dict) -> None:
    fams = ["A", "B", "C"]
    fam = d["by_family"]
    metrics = [
        ("task P", _BLUE, lambda m: m["task"]["precision_mean"]),
        ("task R", _ORANGE, lambda m: m["task"]["recall_mean"]),
        ("edge P", "#9ec5f4", lambda m: m["edge"]["precision_mean"]),
        ("edge R", "#f4b79e", lambda m: m["edge"]["recall_mean"]),
    ]
    width = 0.2
    for i, (name, color, get) in enumerate(metrics):
        xs = [j + (i - 1.5) * width for j in range(len(fams))]
        # a null mean is N/A (no scorable edge set, e.g. family B) — draw nothing
        vals = [get(fam[f]["final"]) or 0.0 for f in fams]
        ax.bar(xs, vals, width=width * 0.9, color=color, label=name)
        for x, f in zip(xs, fams, strict=True):
            if get(fam[f]["final"]) is None:
                ax.text(x, 0.02, "N/A", rotation=90, va="bottom", ha="center",
                        fontsize=7, color=_MUTED)
    ax.set_xticks(range(len(fams)), [f"family {f}\n(n={fam[f]['n']})" for f in fams])
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("precision / recall (macro)", color=_MUTED)
    ax.set_title("Task & edge P/R by family (final)", color=_INK, loc="left", fontweight="bold")
    ax.yaxis.grid(True, color=_GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=8, ncol=4, loc="upper center",
              bbox_to_anchor=(0.5, -0.16))
    _style_axes(ax)


def _panel_latency(ax, d: dict) -> None:
    cases = d["cases"]
    ids = [c["id"] for c in cases]
    lat = [c["latency_s"] for c in cases]
    colors = [_FAMILY_HUE[c["family"]] for c in cases]
    ax.bar(range(len(ids)), lat, color=colors, width=0.62)
    ax.set_xticks(range(len(ids)), ids)
    ax.set_ylabel("seconds", color=_MUTED)
    mean = d["latency_stats"]["mean"]
    ax.axhline(mean, color=_MUTED, lw=1, ls="--")
    ax.text(len(ids) - 0.5, mean, f" mean {mean:.1f}s", va="bottom", ha="right",
            color=_MUTED, fontsize=8)
    ax.set_title("End-to-end latency per case", color=_INK, loc="left", fontweight="bold")
    handles = [plt.Rectangle((0, 0), 1, 1, color=h) for h in _FAMILY_HUE.values()]
    ax.legend(handles, [f"family {k}" for k in _FAMILY_HUE], frameon=False, fontsize=8)
    ax.yaxis.grid(True, color=_GRID, lw=0.8)
    ax.set_axisbelow(True)
    _style_axes(ax)


def figure(run: EvalRun | dict):
    d = run if isinstance(run, dict) else to_dict(run)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2))
    fig.patch.set_facecolor("#fcfcfb")
    _panel_outcomes(axes[0], d)
    _panel_pr(axes[1], d)
    _panel_latency(axes[2], d)
    model = d["meta"].get("model") or d["meta"]["backend_kind"]
    fig.suptitle(
        f"P6 LLM mission decomposition — {model}  "
        f"(scene {d['meta']['scene_hash'][:8]}, validator {d['meta']['validator_version']})",
        color=_INK, fontsize=11, x=0.01, ha="left",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.94))
    return fig


def save(run: EvalRun | dict, out: str | Path) -> list[Path]:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig = figure(run)
    paths = []
    for ext in (".png", ".pdf"):
        p = out.with_suffix(ext)
        fig.savefig(p, dpi=150, facecolor=fig.get_facecolor())
        paths.append(p)
    plt.close(fig)
    return paths


__all__ = ["figure", "save"]
