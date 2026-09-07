"""Deterministic render specs for the operator console (§18.14, D-043/D-044).

A **pure view**: nothing here mutates a session, a scene or a graph, and no
research logic is reimplemented — these functions only lay out values that
``core``/``allocation``/``execution`` already computed.

The determinism gate is the *spec*, not the picture (D-044). A matplotlib
``Figure`` has no equality (``Figure == Figure`` is identity, always False) and
its rendered bytes shift with the matplotlib version, fonts, backend and
metadata, so "same graph, same figure" is untestable. ``DagRenderSpec`` is the
structured value handed to the drawing step — node ids, coordinates, colours,
markers, edges — and *that* is what must be identical for identical input.

Nothing in the spec path imports matplotlib. Drawing does, lazily, so a console
without the optional ``viz`` extra still starts and falls back to the §18.12
tables.
"""

from dataclasses import dataclass

from core.enums import PlatformKind, TaskStatus, TaskType
from core.task_graph import TaskGraph
from interaction.workflow import WORKFLOW_CHAIN

#: §18.14. Every ``TaskStatus`` gets a colour, including ``CANCELLED`` — §10
#: leaves cancellation unsupported so it never appears in a normal run, but the
#: Validator and checkpoints both accept it and a renderer must not raise on a
#: state the data model allows (D-044).
STATUS_COLORS: dict[TaskStatus, str] = {
    TaskStatus.PENDING: "#9e9e9e",      # grey
    TaskStatus.READY: "#1f77b4",        # blue
    TaskStatus.ASSIGNED: "#7b52ab",     # purple
    TaskStatus.RUNNING: "#e8873a",      # orange
    TaskStatus.COMPLETED: "#2e9153",    # green
    TaskStatus.CANCELLED: "#8c1c13",    # dark red
}

#: Short node labels. The full ``task_id`` stays in the spec and in the artist
#: gid, so shortening is presentation-only and never loses the handle.
TYPE_LABELS: dict[TaskType, str] = {
    TaskType.AREA_RECON: "RECON",
    TaskType.THERMAL_RECON: "THERMAL",
    TaskType.SUPPRESSANT_DROP: "DROP",
    TaskType.GROUND_INSPECTION: "INSPECT",
    TaskType.GROUND_SUPPRESSION: "SUPPRESS",
}

#: Marker per platform class, read from ``Task.eligible_platforms`` so the
#: heterogeneous fleet is visible in the picture (§18.14).
UAV_MARKER = "o"
UGV_MARKER = "s"
MIXED_MARKER = "D"

# Same guard style as interaction/workflow.py: a member added to either enum
# must break at import, not at draw time.
assert set(STATUS_COLORS) == set(TaskStatus), "STATUS_COLORS must cover every TaskStatus"
assert set(TYPE_LABELS) == set(TaskType), "TYPE_LABELS must cover every TaskType"

#: Column of each workflow step. AREA_RECON is not a workflow step, so it gets
#: its own column to the left rather than sharing column 0 with THERMAL_RECON —
#: otherwise zone recon markers sit under a "THERMAL" header and the figure
#: reads wrongly.
_STEP_COLUMN: dict[TaskType, int] = {
    step: index for index, step in enumerate(WORKFLOW_CHAIN)
}
_RECON_COLUMN = -1.0


@dataclass(frozen=True, slots=True)
class DagNodeSpec:
    task_id: str
    label: str
    target: str          # the row this node belongs to (zone id or incident id)
    x: float
    y: float
    color: str
    marker: str
    status: TaskStatus

    @property
    def gid(self) -> str:
        return self.task_id


@dataclass(frozen=True, slots=True)
class DagEdgeSpec:
    predecessor: str
    successor: str

    @property
    def gid(self) -> str:
        """Artist handle. Derived rather than stored so the id cannot drift
        away from the endpoints it names."""
        return f"{self.predecessor}->{self.successor}"


@dataclass(frozen=True, slots=True)
class DagRenderSpec:
    nodes: tuple[DagNodeSpec, ...]
    edges: tuple[DagEdgeSpec, ...]
    row_labels: tuple[str, ...]      # top to bottom, one per occupied row
    #: ``(x, label)`` left to right, one per occupied column. Carried here so
    #: the drawing step never needs WORKFLOW_CHAIN — the spec stays the single
    #: source for the picture.
    columns: tuple[tuple[float, str], ...] = ()

    @property
    def task_ids(self) -> frozenset[str]:
        return frozenset(node.task_id for node in self.nodes)

    @property
    def edge_keys(self) -> frozenset[tuple[str, str]]:
        return frozenset((edge.predecessor, edge.successor) for edge in self.edges)


def _natural_key(text: str) -> tuple:
    """Sort FIRE_SITE_2 before FIRE_SITE_10.

    Plain string order would put FIRE_SITE_10 first and make the figure read
    wrongly once a scene passes nine incidents.
    """
    parts: list[object] = []
    digits = ""
    for char in text:
        if char.isdigit():
            digits += char
        else:
            if digits:
                parts.append((1, int(digits), ""))
                digits = ""
            parts.append((0, 0, char))
    if digits:
        parts.append((1, int(digits), ""))
    return tuple(parts)


def _sort_key(text: str) -> tuple:
    """Total order on target ids.

    ``_natural_key`` alone is not one: it parses digits as ints, so
    "FIRE_SITE_2" and "FIRE_SITE_02" collide. Targets are collected into a set
    first, so a tie would leave the row order to set iteration — and therefore
    to ``PYTHONHASHSEED``, which breaks "same graph, same spec". The raw string
    is the tie-break, so no two distinct ids can ever compare equal.
    """
    return (_natural_key(text), text)


def _marker(task) -> str:
    platforms = task.eligible_platforms
    if platforms == frozenset({PlatformKind.UAV}):
        return UAV_MARKER
    if platforms == frozenset({PlatformKind.UGV}):
        return UGV_MARKER
    return MIXED_MARKER


def dag_render_spec(graph: TaskGraph) -> DagRenderSpec:
    """Lay a ``TaskGraph`` out on a deterministic grid (§18.14).

    Row = target, column = workflow step. Zone recon rows come first, then one
    row per incident, each ordered naturally. Position depends only on the
    target id and the task type, never on iteration order or a layout solver,
    so the same graph always yields the same spec — which is what makes a slide
    figure reproducible.

    ``y`` decreases downward so the spec reads top-to-bottom as drawn.
    """
    recon_targets = sorted(
        {t.target for t in graph.tasks if t.task_type is TaskType.AREA_RECON},
        key=_sort_key,
    )
    chain_targets = sorted(
        {t.target for t in graph.tasks if t.task_type is not TaskType.AREA_RECON},
        key=_sort_key,
    )
    row_of = {target: row for row, target in enumerate(recon_targets + chain_targets)}

    nodes = tuple(
        sorted(
            (
                DagNodeSpec(
                    task_id=task.task_id,
                    label=TYPE_LABELS[task.task_type],
                    target=task.target,
                    x=float(_STEP_COLUMN.get(task.task_type, _RECON_COLUMN)),
                    y=float(-row_of[task.target]),
                    color=STATUS_COLORS[task.status],
                    marker=_marker(task),
                    status=task.status,
                )
                for task in graph.tasks
            ),
            key=lambda node: node.task_id,
        )
    )
    edges = tuple(
        DagEdgeSpec(predecessor=pred, successor=succ)
        for pred, succ in sorted(graph.edges)
    )
    chain_types = {t.task_type for t in graph.tasks if t.task_type in _STEP_COLUMN}
    last_column = max((_STEP_COLUMN[t] for t in chain_types), default=-1)
    columns: list[tuple[float, str]] = []
    if recon_targets:
        columns.append((_RECON_COLUMN, TYPE_LABELS[TaskType.AREA_RECON]))
    columns += [
        (float(_STEP_COLUMN[step]), TYPE_LABELS[step])
        for step in WORKFLOW_CHAIN[: last_column + 1]
    ]
    return DagRenderSpec(
        nodes=nodes,
        edges=edges,
        row_labels=tuple(recon_targets + chain_targets),
        columns=tuple(columns),
    )


# -- drawing (§18.14) ---------------------------------------------------
#
# matplotlib is imported inside these functions, never at module scope: the
# console must start when the optional ``viz`` extra is absent and fall back to
# the §18.12 tables (D-044). ``Figure`` is constructed directly with an Agg
# canvas rather than through ``pyplot`` so no global backend or figure registry
# is touched — nothing to leak, nothing to close.

#: Figure height grows with the number of rows but is bounded, so a scene with
#: many incidents produces a tall-ish figure rather than an unusable one.
ROW_HEIGHT_IN = 0.62
MIN_HEIGHT_IN = 2.8
MAX_HEIGHT_IN = 14.0
FIGURE_WIDTH_IN = 9.5


def figure_height(row_count: int) -> float:
    return min(MAX_HEIGHT_IN, max(MIN_HEIGHT_IN, MIN_HEIGHT_IN + ROW_HEIGHT_IN * row_count))


def render_task_graph(spec: DagRenderSpec):
    """Draw a ``DagRenderSpec``. Returns a matplotlib ``Figure``.

    The spec is the **only** data input — no ``TaskGraph``, ``MissionState`` or
    ``Scene`` is read here, which is the point of splitting the layout out: the
    picture cannot disagree with the spec the tests pin. Every node marker and
    every edge arrow carries its identity as the artist ``gid``, so a figure can
    be checked against the spec that produced it before it is saved.
    """
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    rows = len(spec.row_labels)
    fig = Figure(figsize=(FIGURE_WIDTH_IN, figure_height(rows)), dpi=110)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot()

    by_id = {node.task_id: node for node in spec.nodes}
    for edge in spec.edges:
        # Endpoints come from the node coordinates and nowhere else.
        tail, head = by_id[edge.predecessor], by_id[edge.successor]
        arrow = ax.annotate(
            "",
            xy=(head.x, head.y),
            xytext=(tail.x, tail.y),
            arrowprops={"arrowstyle": "-|>", "color": "#5b6470", "linewidth": 1.1,
                        "shrinkA": 13, "shrinkB": 13},
        )
        arrow.set_gid(edge.gid)

    for node in spec.nodes:
        marker = ax.plot(
            [node.x], [node.y],
            marker=node.marker, markersize=15,
            color=node.color, markeredgecolor="#2b2f36", markeredgewidth=0.8,
            linestyle="none", zorder=3,
        )[0]
        marker.set_gid(node.gid)
        ax.annotate(
            node.label, (node.x, node.y), textcoords="offset points",
            xytext=(0, 13), ha="center", fontsize=7.5, color="#2b2f36",
        )

    ax.set_xticks([x for x, _ in spec.columns])
    ax.set_xticklabels([label for _, label in spec.columns], fontsize=8)
    ax.xaxis.set_ticks_position("top")
    ax.set_yticks([-row for row in range(rows)])
    ax.set_yticklabels(spec.row_labels, fontsize=8)
    xs = [x for x, _ in spec.columns] or [0.0]
    ax.set_xlim(min(xs) - 0.7, max(xs) + 0.7)
    ax.set_ylim(-(rows - 1) - 0.7 if rows else -0.7, 0.7)
    for side in ("top", "right", "bottom", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    ax.grid(axis="y", color="#e8eaed", linewidth=0.8)
    ax.set_axisbelow(True)

    status_legend = ax.legend(
        handles=[
            Patch(facecolor=STATUS_COLORS[status], edgecolor="#2b2f36",
                  linewidth=0.6, label=status.value)
            for status in TaskStatus
        ],
        title="TaskStatus", loc="upper left", bbox_to_anchor=(1.01, 1.0),
        fontsize=7.5, title_fontsize=8, frameon=False,
    )
    ax.add_artist(status_legend)   # keep it when the second legend is added
    ax.legend(
        handles=[
            Line2D([], [], marker=marker, linestyle="none", markersize=8,
                   color="#ffffff", markeredgecolor="#2b2f36", label=label)
            for marker, label in (
                (UAV_MARKER, "UAV"), (UGV_MARKER, "UGV"), (MIXED_MARKER, "UAV/UGV"),
            )
        ],
        title="Platform", loc="lower left", bbox_to_anchor=(1.01, 0.0),
        fontsize=7.5, title_fontsize=8, frameon=False,
    )
    fig.tight_layout()
    return fig


__all__ = [
    "STATUS_COLORS",
    "TYPE_LABELS",
    "UAV_MARKER",
    "UGV_MARKER",
    "MIXED_MARKER",
    "DagNodeSpec",
    "DagEdgeSpec",
    "DagRenderSpec",
    "dag_render_spec",
    "figure_height",
    "render_task_graph",
]
