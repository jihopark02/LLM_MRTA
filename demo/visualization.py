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

from allocation.allocate import AllocationResult
from allocation.travel import start_ref, task_ref
from core.enums import PlatformKind, TaskStatus, TaskType
from core.task_graph import TaskGraph
from execution.executor import ExecutionResult, SimExecutor
from interaction.workflow import WORKFLOW_CHAIN
from scenarios.scene import Scene

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


# -- 2D mission map spec (§18.14) ---------------------------------------

#: Fixed per-agent colours, assigned by sorted agent id so the same agent is
#: the same colour in every mode and every run.
AGENT_COLORS = (
    "#1f77b4", "#e8873a", "#2e9153", "#8c1c13",
    "#7b52ab", "#0f8b8d", "#b5651d", "#4c566a",
)

#: How a leg is drawn. ``in_progress`` is dashed because it is *not* an
#: interpolated pose — it joins an agent's last confirmed position to the
#: target it is travelling toward (§18.14, D-044).
LEG_LINESTYLES = {
    "planned": "solid",
    "completed": "solid",
    "in_progress": "dashed",
    "remaining": "dotted",
}
MAP_MODES = ("plan", "runtime", "execution")


@dataclass(frozen=True, slots=True)
class MapPointSpec:
    entity_id: str
    x: float
    y: float
    kind: str            # zone | incident | task
    label: str


@dataclass(frozen=True, slots=True)
class AgentMapSpec:
    """Where an agent is *in the moment the map depicts*.

    plan: its start, since nothing has run. runtime: its last confirmed
    position (never an interpolated pose, D-044). execution: where it ended.
    """

    agent_id: str
    platform_kind: PlatformKind
    color: str
    position: tuple[float, float]


@dataclass(frozen=True, slots=True)
class MapLegSpec:
    agent_id: str
    task_id: str
    order: int
    points: tuple[tuple[float, float], ...]
    phase: str

    @property
    def linestyle(self) -> str:
        return LEG_LINESTYLES[self.phase]

    @property
    def gid(self) -> str:
        return f"{self.agent_id}:{self.order}:{self.phase}:{self.task_id}"


@dataclass(frozen=True, slots=True)
class MapRenderSpec:
    mode: str
    zones: tuple[MapPointSpec, ...]
    incidents: tuple[MapPointSpec, ...]
    route_lanes: tuple[tuple[tuple[float, float], ...], ...]
    agents: tuple[AgentMapSpec, ...]
    task_points: tuple[MapPointSpec, ...]
    legs: tuple[MapLegSpec, ...]
    simulation_time: float | None = None


def _agent_colors(scene: Scene) -> dict[str, str]:
    return {
        agent.agent_id: AGENT_COLORS[index % len(AGENT_COLORS)]
        for index, agent in enumerate(sorted(scene.fleet, key=lambda a: a.agent_id))
    }


def _ref_point(ref, scene: Scene) -> tuple[float, float]:
    """A LegRef as a 2D point: a UAV ref already is one, a UGV ref is a node."""
    if isinstance(ref, str):
        return tuple(scene.route_graph.position(ref))
    return (float(ref[0]), float(ref[1]))


def _uav_leg_points(from_ref, to_ref, scene: Scene):
    """A straight hop — exactly two points (§8: UAV travel is Euclidean)."""
    return (_ref_point(from_ref, scene), _ref_point(to_ref, scene))


def _ugv_leg_points(from_node: str, to_node: str, scene: Scene):
    """The lanes a UGV actually drives.

    ``RouteGraph.shortest_path_nodes`` is the only source (D-044) — computing a
    route here would duplicate the allocator's own decision and could disagree
    with the distance it bid on.
    """
    nodes = scene.route_graph.shortest_path_nodes(from_node, to_node)
    if nodes is None:
        return ()
    return tuple(tuple(scene.route_graph.position(node)) for node in nodes)


def _leg_points(agent, from_ref, task, scene: Scene):
    destination = task_ref(agent, task, scene)
    if agent.platform_kind is PlatformKind.UAV:
        return _uav_leg_points(from_ref, destination, scene), destination
    return _ugv_leg_points(from_ref, destination, scene), destination


def _scene_background(scene: Scene):
    """Zones, incidents and lanes — identical whichever mode is drawn."""
    zones = tuple(
        MapPointSpec(zid, *map(float, zone.recon_waypoint), "zone", zone.name)
        for zid, zone in sorted(scene.zones.items())
    )
    incidents = tuple(
        MapPointSpec(iid, *map(float, incident.position), "incident", iid)
        for iid, incident in sorted(scene.incidents.items())
    )
    lanes = tuple(
        (tuple(scene.route_graph.position(a)), tuple(scene.route_graph.position(b)))
        for a, b, _ in scene.route_graph.lanes
    )
    return zones, incidents, lanes


def _task_points(graph: TaskGraph):
    return tuple(
        MapPointSpec(
            task.task_id, float(task.position[0]), float(task.position[1]),
            "task", TYPE_LABELS[task.task_type],
        )
        for task in sorted(graph.tasks, key=lambda t: t.task_id)
    )


def _ordered_for_agent(assignments: dict[str, str], times: dict[str, float]):
    """agent_id -> task ids in execution order.

    Ordered by the recorded time, never by task id or graph order: drawing a
    route in alphabetical order would show a path nobody drove.
    """
    per_agent: dict[str, list[str]] = {}
    for task_id, agent_id in assignments.items():
        if task_id in times:
            per_agent.setdefault(agent_id, []).append(task_id)
    return {
        agent_id: sorted(task_ids, key=lambda t: (times[t], t))
        for agent_id, task_ids in per_agent.items()
    }


def _walk(agent, task_ids, graph, scene, phase, start):
    """Chain legs from ``start``, returning the specs and the final ref."""
    legs, current = [], start
    for order, task_id in enumerate(task_ids):
        points, current = _leg_points(agent, current, graph[task_id], scene)
        if points:
            legs.append(MapLegSpec(agent.agent_id, task_id, order, points, phase))
    return legs, current


def plan_map_spec(
    scene: Scene, graph: TaskGraph, plan: AllocationResult
) -> MapRenderSpec:
    """The route the plan-time analysis intends (§18.14). Nothing has run."""
    colors = _agent_colors(scene)
    order = _ordered_for_agent(plan.assignments, plan.task_start)
    zones, incidents, lanes = _scene_background(scene)
    legs: list[MapLegSpec] = []
    agents: list[AgentMapSpec] = []
    for agent in sorted(scene.fleet, key=lambda a: a.agent_id):
        start = start_ref(agent, scene)
        agents.append(
            AgentMapSpec(
                agent.agent_id, agent.platform_kind, colors[agent.agent_id],
                _ref_point(start, scene),
            )
        )
        walked, _ = _walk(
            agent, order.get(agent.agent_id, ()), graph, scene, "planned", start
        )
        legs += walked
    return MapRenderSpec(
        mode="plan",
        zones=zones,
        incidents=incidents,
        route_lanes=lanes,
        agents=tuple(agents),
        task_points=_task_points(graph),
        legs=tuple(legs),
    )


def execution_map_spec(
    scene: Scene, graph: TaskGraph, result: ExecutionResult
) -> MapRenderSpec:
    """What actually happened (§18.14).

    Only tasks with a recorded departure are drawn: a task that was released
    and rebid away never left, so it is not part of anyone's route.
    """
    colors = _agent_colors(scene)
    order = _ordered_for_agent(result.assignments, result.task_departure)
    zones, incidents, lanes = _scene_background(scene)
    legs: list[MapLegSpec] = []
    agents: list[AgentMapSpec] = []
    for agent in sorted(scene.fleet, key=lambda a: a.agent_id):
        start = start_ref(agent, scene)
        walked, final = _walk(
            agent, order.get(agent.agent_id, ()), graph, scene, "completed", start
        )
        legs += walked
        # The run is over, so the marker is where the agent ended — the same
        # rule as the other two modes: it shows where the agent is in the
        # moment this map depicts (start for a plan, last confirmed while
        # paused). An agent that drew no leg never moved.
        agents.append(
            AgentMapSpec(
                agent.agent_id, agent.platform_kind, colors[agent.agent_id],
                _ref_point(final, scene),
            )
        )
    return MapRenderSpec(
        mode="execution",
        zones=zones,
        incidents=incidents,
        route_lanes=lanes,
        agents=tuple(agents),
        task_points=_task_points(graph),
        legs=tuple(legs),
        simulation_time=result.makespan,
    )


def runtime_map_spec(scene: Scene, runtime: SimExecutor) -> MapRenderSpec:
    """A paused online run (§18.14, D-044).

    Read from a checkpoint taken here, so the live executor is never touched.
    An agent is drawn at its **last confirmed position** — the simulator only
    updates a position when a task completes, so there is no current pose to
    draw and none is invented. A RUNNING task becomes a dashed leg from that
    position to its target; not-yet-started assignments follow the agent's own
    path order.
    """
    checkpoint = runtime.checkpoint()
    work = checkpoint._work                     # read-only, never handed out
    graph = work.graph
    colors = _agent_colors(scene)
    access = dict(checkpoint.access_nodes)
    sim = dict(checkpoint.sim)
    departures = dict(checkpoint.task_departure)
    done_order = _ordered_for_agent(dict(checkpoint.assignments), departures)

    zones, incidents, lanes = _scene_background(scene)
    legs: list[MapLegSpec] = []
    agents: list[AgentMapSpec] = []
    for agent_id in sorted(work.agents):
        agent = work.agents[agent_id]
        scene_agent = next(a for a in scene.fleet if a.agent_id == agent_id)
        start = start_ref(scene_agent, scene)

        completed = [
            task_id
            for task_id in done_order.get(agent_id, ())
            if graph[task_id].status is TaskStatus.COMPLETED
        ]
        walked, _ = _walk(agent, completed, graph, scene, "completed", start)
        legs += walked

        # Last confirmed position: updated only on completion, never interpolated.
        confirmed = (
            agent.position
            if agent.platform_kind is PlatformKind.UAV
            else access.get(agent_id)
        )
        agents.append(
            AgentMapSpec(
                agent_id, agent.platform_kind, colors[agent_id],
                _ref_point(confirmed, scene),
            )
        )

        current = confirmed
        running = sim[agent_id].current
        order = len(completed)
        if running is not None:
            points, current = _leg_points(agent, current, graph[running], scene)
            if points:
                legs.append(MapLegSpec(agent_id, running, order, points, "in_progress"))
            order += 1
        for task_id in [t for t in agent.path if t != running]:
            points, current = _leg_points(agent, current, graph[task_id], scene)
            if points:
                legs.append(MapLegSpec(agent_id, task_id, order, points, "remaining"))
            order += 1

    legs.sort(key=lambda leg: (leg.agent_id, leg.order))
    return MapRenderSpec(
        mode="runtime",
        zones=zones,
        incidents=incidents,
        route_lanes=lanes,
        agents=tuple(agents),
        task_points=_task_points(graph),
        legs=tuple(legs),
        simulation_time=checkpoint.now,
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


#: Title per mode. The three maps are never overlaid — the operator must be able
#: to tell an intended plan from what actually ran (§18.14).
MAP_MODE_TITLES = {
    "plan": "Plan-time CBBA — intended route (nothing has run)",
    "runtime": "Online execution paused — last confirmed positions",
    "execution": "Completed execution — route actually driven",
}
MAP_WIDTH_IN = 9.5
MAP_HEIGHT_IN = 7.0
_MAP_PAD = 0.06          # fraction of the drawn extent added as margin


def _map_bounds(spec: "MapRenderSpec"):
    xs, ys = [], []
    for point in spec.zones + spec.incidents + spec.task_points:
        xs.append(point.x)
        ys.append(point.y)
    for agent in spec.agents:
        xs.append(agent.position[0])
        ys.append(agent.position[1])
    for lane in spec.route_lanes:
        for x, y in lane:
            xs.append(x)
            ys.append(y)
    for leg in spec.legs:
        for x, y in leg.points:
            xs.append(x)
            ys.append(y)
    if not xs:
        return (-1.0, 1.0, -1.0, 1.0)
    pad = max(max(xs) - min(xs), max(ys) - min(ys)) * _MAP_PAD or 1.0
    return (min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad)


def render_mission_map(spec: MapRenderSpec):
    """Draw a ``MapRenderSpec``. Returns a matplotlib ``Figure``.

    One renderer for all three modes (§18.14): separate ones would let the
    background, colours, legends and line styles drift apart between a plan and
    the run it is compared against. The spec is the only data input — no
    ``Scene``, executor or result is read here.
    """
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from matplotlib.lines import Line2D

    fig = Figure(figsize=(MAP_WIDTH_IN, MAP_HEIGHT_IN), dpi=110)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot()

    # Route graph first, as a neutral backdrop.
    for lane in spec.route_lanes:
        ax.plot(
            [x for x, _ in lane], [y for _, y in lane],
            color="#d5d9de", linewidth=1.6, zorder=0, solid_capstyle="round",
        )

    for zone in spec.zones:
        ax.plot([zone.x], [zone.y], marker="P", markersize=11, linestyle="none",
                color="#c9ced6", markeredgecolor="#98a0ab", zorder=1)
        ax.annotate(zone.label, (zone.x, zone.y), textcoords="offset points",
                    xytext=(0, 11), ha="center", fontsize=7, color="#6b7280")
    for incident in spec.incidents:
        ax.plot([incident.x], [incident.y], marker="X", markersize=12,
                linestyle="none", color="#c0392b", markeredgecolor="#7b1e14", zorder=2)
        ax.annotate(incident.entity_id, (incident.x, incident.y),
                    textcoords="offset points", xytext=(0, -15), ha="center",
                    fontsize=7, color="#7b1e14")
    for task in spec.task_points:
        ax.plot([task.x], [task.y], marker=".", markersize=6, linestyle="none",
                color="#4c566a", zorder=2)

    colors = {agent.agent_id: agent.color for agent in spec.agents}
    for leg in spec.legs:
        if len(leg.points) < 2:
            continue                     # a zero-length hop draws nothing
        line = ax.plot(
            [x for x, _ in leg.points], [y for _, y in leg.points],
            color=colors.get(leg.agent_id, "#4c566a"),
            linestyle=leg.linestyle, linewidth=1.8, zorder=4, solid_capstyle="round",
        )[0]
        line.set_gid(leg.gid)
        end_x, end_y = leg.points[-1]
        ax.annotate(
            str(leg.order + 1), (end_x, end_y), textcoords="offset points",
            xytext=(6, 6), fontsize=7, zorder=5,
            color=colors.get(leg.agent_id, "#4c566a"),
        )

    for agent in spec.agents:
        marker = UAV_MARKER if agent.platform_kind is PlatformKind.UAV else UGV_MARKER
        ax.plot(
            [agent.position[0]], [agent.position[1]],
            marker=marker, markersize=13, linestyle="none",
            color=agent.color, markeredgecolor="#2b2f36", markeredgewidth=0.9, zorder=6,
        )

    title = MAP_MODE_TITLES.get(spec.mode, spec.mode)
    if spec.simulation_time is not None:
        title += f"  ·  t = {spec.simulation_time:.1f} s"
    ax.set_title(title, fontsize=10, loc="left")

    left, right, bottom, top = _map_bounds(spec)
    ax.set_xlim(left, right)
    ax.set_ylim(bottom, top)
    ax.set_aspect("equal", adjustable="box")
    ax.tick_params(labelsize=7, colors="#6b7280")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)

    agent_legend = ax.legend(
        handles=[
            Line2D([], [], marker=(UAV_MARKER if a.platform_kind is PlatformKind.UAV
                                   else UGV_MARKER),
                   linestyle="none", markersize=8, color=a.color,
                   markeredgecolor="#2b2f36", label=a.agent_id)
            for a in spec.agents
        ],
        title="Agents", loc="upper left", bbox_to_anchor=(1.01, 1.0),
        fontsize=7.5, title_fontsize=8, frameon=False,
    )
    ax.add_artist(agent_legend)
    # Only the phases this map actually contains: a plan has nothing dashed,
    # and listing "planned" beside "completed" (both solid) reads as a
    # distinction the picture is not making.
    drawn_phases = {leg.phase for leg in spec.legs}
    present = [phase for phase in LEG_LINESTYLES if phase in drawn_phases]
    if present:
        ax.legend(
            handles=[
                Line2D([], [], color="#4c566a", linestyle=LEG_LINESTYLES[phase], label=phase)
                for phase in present
            ],
            title="Leg", loc="lower left", bbox_to_anchor=(1.01, 0.0),
            fontsize=7.5, title_fontsize=8, frameon=False,
        )
    fig.tight_layout()
    return fig


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
    "AGENT_COLORS",
    "LEG_LINESTYLES",
    "MAP_MODES",
    "MapPointSpec",
    "AgentMapSpec",
    "MapLegSpec",
    "MapRenderSpec",
    "plan_map_spec",
    "runtime_map_spec",
    "execution_map_spec",
    "figure_height",
    "render_task_graph",
    "MAP_MODE_TITLES",
    "render_mission_map",
]
