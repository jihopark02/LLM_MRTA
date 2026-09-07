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

#: Column of each workflow step; AREA_RECON has no step and sits in column 0 of
#: its own zone rows, so no two tasks ever share a cell.
_STEP_COLUMN: dict[TaskType, int] = {
    step: index for index, step in enumerate(WORKFLOW_CHAIN)
}


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

    @property
    def task_ids(self) -> frozenset[str]:
        return frozenset(node.task_id for node in self.nodes)

    @property
    def edge_keys(self) -> frozenset[tuple[str, str]]:
        return frozenset((edge.predecessor, edge.successor) for edge in self.edges)


def _natural_key(text: str) -> tuple:
    """Sort FIRE_SITE_2 before FIRE_SITE_10.

    Plain string order would put FIRE_SITE_10 first and make the figure read
    wrongly once a scene passes nine incidents. Still fully deterministic.
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
        key=_natural_key,
    )
    chain_targets = sorted(
        {t.target for t in graph.tasks if t.task_type is not TaskType.AREA_RECON},
        key=_natural_key,
    )
    row_of = {target: row for row, target in enumerate(recon_targets + chain_targets)}

    nodes = tuple(
        sorted(
            (
                DagNodeSpec(
                    task_id=task.task_id,
                    label=TYPE_LABELS[task.task_type],
                    target=task.target,
                    x=float(_STEP_COLUMN.get(task.task_type, 0)),
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
    return DagRenderSpec(
        nodes=nodes,
        edges=edges,
        row_labels=tuple(recon_targets + chain_targets),
    )


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
]
