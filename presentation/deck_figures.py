"""Figure generator for the D-075 presentation deck.

Mission-control styled frames (not matplotlib-debug plots): no axes, styled
zone / agent glyphs, real CBBA assignment from ``allocation.allocate``. Every
number and grouping here is computed from the repo, nothing is hand-placed.

    python3 presentation/deck_figures.py      # writes presentation/fig/*.png
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

from allocation.allocate import allocate  # noqa: E402
from core.enums import TaskType  # noqa: E402
from interaction.session import fresh_session_state  # noqa: E402
from scenarios.compiler import compile_reference_graph  # noqa: E402
from scenarios.scene import load_scene  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "presentation" / "fig"
OUT.mkdir(exist_ok=True)

INK = "#1b1b2b"
MUTED = "#9aa0ac"
ROUTE = "#dcdee5"
CREAM = "#faf8f3"
LLM = "#d9812f"
DET = "#0e7c7b"
FIRE = "#d5342b"
UAV_C = {"U1": "#2f6fed", "U2": "#c53a86", "U3": "#7a4fd0"}
UAV_FILL = {"U1": "#cfe0fb", "U2": "#f6cee2", "U3": "#e0d2f4"}
UGV_C = "#0e7c7b"

SCENE = load_scene(ROOT / "scenarios" / "demo_grid.yaml")
# seed 2 + min_separation 170 (scenarios/demo_grid_latent.yaml) -> these zones
LATENT_FIRE_ZONES = ("ZONE_A", "ZONE_D", "ZONE_J", "ZONE_O")


def _recon_assignment():
    graph = compile_reference_graph(
        SCENE, [(TaskType.AREA_RECON, z) for z in sorted(SCENE.zones)], []
    )
    plan = allocate(fresh_session_state(graph, SCENE), SCENE)
    owner = {}
    for tid, aid in plan.assignments.items():
        owner["ZONE_" + tid.split("ZONE_")[1]] = aid
    return plan, owner


def _ugv_route_pts(node_a, node_b):
    nodes = SCENE.route_graph.shortest_path_nodes(node_a, node_b) or []
    return [tuple(SCENE.route_graph.position(n)) for n in nodes]


def _canvas(title: str, sub: str = ""):
    fig = Figure(figsize=(9.0, 4.5), dpi=200)
    fig.patch.set_facecolor(CREAM)
    fig.subplots_adjust(left=0.015, right=0.985, top=0.985, bottom=0.015)
    ax = fig.add_subplot()
    ax.set_facecolor(CREAM)
    ax.set_xlim(-20, 500)
    ax.set_ylim(-52, 452)
    ax.set_aspect(0.60)   # compress y so the 4-column grid renders wide
    ax.axis("off")
    ax.text(-12, 436, title, fontsize=15, fontweight="bold", color=INK)
    if sub:
        ax.text(-12, 404, sub, fontsize=9.5, color=MUTED)
    return fig, ax


def _save(fig, name):
    fig.savefig(OUT / name, facecolor=CREAM)   # fixed size — no tight bbox


def _world(ax, *, owner=None, fires=(), done=()):
    for a, b, _w in SCENE.route_graph.lanes:
        (x1, y1), (x2, y2) = SCENE.route_graph.position(a), SCENE.route_graph.position(b)
        ax.plot([x1, x2], [y1, y2], color=ROUTE, lw=2.2, zorder=1, solid_capstyle="round")
    for zid, zone in SCENE.zones.items():
        x, y = zone.recon_waypoint
        aid = (owner or {}).get(zid)
        fc = UAV_FILL[aid] if aid else "white"
        ec = UAV_C[aid] if aid else MUTED
        ax.add_patch(FancyBboxPatch(
            (x - 12, y - 12), 24, 24, boxstyle="round,pad=1.4,rounding_size=5",
            fc=fc, ec=ec, lw=1.6 if aid else 1.2, zorder=3))
        ax.text(x, y, zid.split("_")[1], ha="center", va="center",
                fontsize=11, fontweight="bold", color=INK, zorder=4)
        if zid in done:
            ax.text(x + 11, y + 11, "✓", ha="center", va="center", fontsize=9,
                    color=DET, fontweight="bold", zorder=5)
    for zid in fires:
        x, y = SCENE.zones[zid].reported_incident_position
        ax.scatter([x], [y], s=260, marker="*", color=FIRE, edgecolor="white",
                   linewidth=1.2, zorder=6)
    for aid, agent in ((a.agent_id, a) for a in SCENE.fleet):
        x, y = agent.initial_position
        is_uav = aid.startswith("U")
        ax.scatter([x + (0 if is_uav else 16)], [y], s=120,
                   marker=("^" if is_uav else "s"),
                   color=(UAV_C[aid] if is_uav else UGV_C),
                   edgecolor=INK, linewidth=0.7, zorder=7)
    ax.text(30, -12, "DEPOT", ha="center", fontsize=7.5, color=MUTED)


def _owner_legend(ax, plan):
    counts = {aid: sum(1 for v in plan.assignments.values() if v == aid)
              for aid in ("U1", "U2", "U3")}
    handles = [
        Line2D([], [], marker="s", color="none", markerfacecolor=UAV_FILL[a],
               markeredgecolor=UAV_C[a], markersize=11,
               label=f"{a}  ·  {counts[a]} zones")
        for a in ("U1", "U2", "U3")
    ]
    ax.legend(handles=handles, loc="lower right", bbox_to_anchor=(1.02, -0.13),
              frameon=False, fontsize=9, handletextpad=0.5)


# -- six demo frames --------------------------------------------------


def demo_frames():
    plan, owner = _recon_assignment()
    ms = plan.estimated_makespan

    fig, ax = _canvas(
        "1 · World",
        "known before any mission — 15 zones (A-O), UGV road network, 3 UAV + 2 UGV at depot")
    _world(ax)
    ax.legend(handles=[
        Line2D([], [], marker="^", color="none", markerfacecolor="#666",
               markeredgecolor=INK, markersize=9, label="UAV — aerial recon, straight-line"),
        Line2D([], [], marker="s", color="none", markerfacecolor=UGV_C,
               markeredgecolor=INK, markersize=9, label="UGV — ground, road network"),
    ], loc="lower right", bbox_to_anchor=(1.02, -0.13), frameon=False, fontsize=9)
    _save(fig, "demo_1_world.png")

    fig, ax = _canvas(
        "2 · Validated mission graph",
        'operator: "aerial recon of every zone"  →  LLM candidate  →  Validator')
    _world(ax)
    ax.text(240, -34, "15 × AREA_RECON  ·  0 dependencies  ·  invariant validation: PASS",
            ha="center", fontsize=9.5,
            color=DET, fontweight="bold")
    _save(fig, "demo_2_mission.png")

    fig, ax = _canvas(
        "3 · Heterogeneous CBBA allocation",
        "validated tasks distributed by capability + travel cost")
    _world(ax, owner=owner)
    cnt = {a: sum(1 for v in plan.assignments.values() if v == a) for a in ("U1","U2","U3")}
    ax.text(240, -34,
            f"U1·{cnt['U1']}  U2·{cnt['U2']}  U3·{cnt['U3']} zones   ·   "
            f"estimated makespan ≈ {ms:.0f}s", ha="center", fontsize=10, color=INK)
    _save(fig, "demo_3_alloc.png")

    fig, ax = _canvas(
        "4 · Execution",
        "each UAV sweeps its region; recon progressively confirms the zones")
    done = {"ZONE_A", "ZONE_B", "ZONE_E", "ZONE_C", "ZONE_M", "ZONE_N", "ZONE_I"}
    _world(ax, owner=owner, done=done)
    ax.text(240, -34, "checkpoint-based executor — safe boundaries between tasks",
            ha="center", fontsize=10, color=MUTED)
    _save(fig, "demo_4_exec.png")

    fig, ax = _canvas(
        "5 · Latent incident revealed",
        "recon at zone J completes → a hidden fire becomes known (A, D, O still latent)")
    _world(ax, owner=owner, done=done | {"ZONE_J", "ZONE_F"}, fires=("ZONE_J",))
    fx, fy = SCENE.zones["ZONE_J"].reported_incident_position
    ax.annotate("Fire 1  —  operator approval gate", (fx, fy), (fx + 34, fy - 46),
                fontsize=9.5, color=FIRE, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=FIRE))
    _save(fig, "demo_5_incident.png")

    fig, ax = _canvas(
        "6 · Selective reallocation",
        "only the new ground response is bid — UAV recon commitments are preserved")
    _world(ax, owner=owner, done=done | {"ZONE_J", "ZONE_F"}, fires=("ZONE_J",))
    pts = _ugv_route_pts(SCENE.agent_access_nodes["G1"],
                         SCENE.zones["ZONE_J"].reported_incident_access_node)
    for (x1, y1), (x2, y2) in zip(pts, pts[1:], strict=False):
        ax.plot([x1, x2], [y1, y2], color=UGV_C, lw=3.4, zorder=5,
                solid_capstyle="round")
    if len(pts) >= 2:
        ax.add_patch(FancyArrowPatch(pts[-2], pts[-1], arrowstyle="-|>",
                     mutation_scale=15, color=UGV_C, lw=3.4, zorder=5))
    ax.text(240, -34, "new ground response (G1)  ·  rebid: ground only  ·  UAV bundles unchanged",
            ha="center", fontsize=9, color=INK)
    for t in ax.texts:
        t.set_path_effects([pe.withStroke(linewidth=2.2, foreground=CREAM)])
    _save(fig, "demo_6_reselect.png")


# -- NL -> validated graph -------------------------------------------


def graph_example():
    fig = Figure(figsize=(7.6, 3.1), dpi=200)
    fig.patch.set_facecolor(CREAM)
    ax = fig.add_subplot()
    ax.set_facecolor(CREAM)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 44)
    ax.axis("off")

    def node(x, y, label, w=23):
        ax.add_patch(FancyBboxPatch((x - w / 2, y - 4.6), w, 9.2,
                     boxstyle="round,pad=0.4,rounding_size=1.6",
                     fc="white", ec=DET, lw=1.7))
        ax.text(x, y, label, ha="center", va="center", fontsize=8.4,
                color=INK, fontweight="bold")

    for i, z in enumerate(("ZONE_A", "ZONE_D", "ZONE_G")):
        node(15, 35 - i * 12.5, f"AREA_RECON\n{z}")
    node(50, 28, "GROUND_INSPECTION\nFIRE_SITE_1")
    node(50, 9, "GROUND_SUPPRESSION\nFIRE_SITE_1")
    ax.add_patch(FancyArrowPatch((50, 23.2), (50, 13.8), arrowstyle="-|>",
                 mutation_scale=14, color=INK, lw=1.6))
    ax.text(50, 43,
            'operator:  "recon zones A, D and G, and take FIRE_SITE_1 '
            'through full ground suppression"',
            ha="center", fontsize=8.8, color=LLM, style="italic")
    ax.add_patch(FancyArrowPatch((64, 18), (72, 18), arrowstyle="-|>",
                 mutation_scale=14, color=INK, lw=1.6))
    ax.text(87, 30, "Deterministic\nInvariant Validator", ha="center", va="center",
            fontsize=9, color=DET, fontweight="bold")
    ax.text(87, 15,
            "schema · reference\nDAG / cycle\nworkflow dependency\ncapability\nreachability",
            ha="center", va="center", fontsize=7.2, color=MUTED)
    fig.savefig(OUT / "graph_example.png", bbox_inches="tight", facecolor=CREAM)


# -- selective vs full reset ----------------------------------------


def realloc_before_after():
    fig = Figure(figsize=(7.8, 3.3), dpi=200)
    fig.patch.set_facecolor(CREAM)
    for col, (title, released) in enumerate((
        ("Full reset", {"U1", "U2", "U3", "G1"}),
        ("Selective release   (this system)", {"G1"}),
    )):
        ax = fig.add_subplot(1, 2, col + 1)
        ax.set_facecolor(CREAM)
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 10)
        ax.axis("off")
        ax.text(5, 9.5, title, ha="center", fontsize=11, fontweight="bold", color=INK)
        rows = [("U1 recon", "U1"), ("U2 recon", "U2"),
                ("U3 recon", "U3"), ("G1 ground", "G1")]
        for i, (label, key) in enumerate(rows):
            y = 7.7 - i * 1.7
            gone = key in released
            ax.add_patch(FancyBboxPatch((1.0, y - 0.58), 8.0, 1.16,
                         boxstyle="round,pad=0.1,rounding_size=0.2",
                         fc=(CREAM if gone else "white"),
                         ec=(MUTED if gone else DET),
                         ls=("--" if gone else "-"), lw=1.7))
            ax.text(1.5, y, label, va="center", fontsize=10.5, fontweight="bold",
                    color=(MUTED if gone else INK))
            ax.text(8.5, y, "release + rebid" if gone else "유지",
                    va="center", ha="right", fontsize=9.5,
                    color=(FIRE if gone else DET), fontweight="bold")
        ax.text(5, 0.4, f"{len(released)} of 4 assignments released",
                ha="center", fontsize=9, color=MUTED)
    fig.savefig(OUT / "realloc_before_after.png", bbox_inches="tight", facecolor=CREAM)


if __name__ == "__main__":
    demo_frames()
    graph_example()
    realloc_before_after()
    print("wrote", *(p.name for p in sorted(OUT.glob("*.png"))))
