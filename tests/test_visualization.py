"""P8.5a gate: the deterministic DAG render spec (§18.14, D-043/D-044).

The determinism gate is the spec, never the image: a matplotlib ``Figure`` has
no equality and its bytes move with the matplotlib version, fonts and backend
(D-044). Everything here is checked on the structured value.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from core.enums import PlatformKind, TaskStatus, TaskType
from demo.visualization import (
    MIXED_MARKER,
    STATUS_COLORS,
    TYPE_LABELS,
    UAV_MARKER,
    UGV_MARKER,
    _natural_key,
    _sort_key,
    dag_render_spec,
)
from interaction.ground import build_chain_patch
from interaction.scene_mut import register_incident
from interaction.session import fresh_session_state
from scenarios.fixture import load_reference_fixture
from scenarios.scene import load_scene
from validator.hashing import pre_state_hash, scene_hash
from validator.patch_apply import apply_patch

SCENARIOS = Path(__file__).parents[1] / "scenarios"


@pytest.fixture
def scene():
    return load_scene(SCENARIOS / "industrial_park.yaml")


@pytest.fixture
def graph():
    return load_reference_fixture().graph


# -- the spec must not need matplotlib (D-044 degrade path) --------------


def test_building_a_spec_never_imports_matplotlib():
    # In a subprocess, because another test in the session may already have
    # imported matplotlib — an in-process check would silently degrade to a
    # skip. This is what lets the console start without the viz extra (D-044).
    probe = (
        "import sys;"
        "import demo.visualization as v;"
        "from scenarios.fixture import load_reference_fixture;"
        "v.dag_render_spec(load_reference_fixture().graph);"
        "hit=[n for n in sys.modules if n=='matplotlib' or n.startswith('matplotlib.')];"
        "print('LEAK' if hit else 'CLEAN')"
    )
    done = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
        check=True,
    )
    assert done.stdout.strip() == "CLEAN", done.stdout


# -- colour / label tables cover the enums ------------------------------


def test_every_task_status_has_a_colour():
    # Iterating the enum, not a hand-written list: adding a TaskStatus member
    # must break here rather than at draw time (D-044).
    assert set(STATUS_COLORS) == set(TaskStatus)
    assert len(set(STATUS_COLORS.values())) == len(TaskStatus), "colours must be distinct"
    assert TaskStatus.CANCELLED in STATUS_COLORS


def test_every_task_type_has_a_label():
    assert set(TYPE_LABELS) == set(TaskType)
    assert len(set(TYPE_LABELS.values())) == len(TaskType)


# -- spec agrees with the graph -----------------------------------------


def test_spec_nodes_are_exactly_the_graph_tasks(graph):
    spec = dag_render_spec(graph)
    assert spec.task_ids == {task.task_id for task in graph.tasks}
    assert len(spec.nodes) == len(graph)


def test_spec_edges_are_exactly_the_graph_edges(graph):
    spec = dag_render_spec(graph)
    assert spec.edge_keys == graph.edges
    assert len(spec.edges) == len(graph.edges)


def test_every_node_carries_its_status_colour_and_platform_marker(graph):
    spec = dag_render_spec(graph)
    for node in spec.nodes:
        task = graph[node.task_id]
        assert node.status is task.status
        assert node.color == STATUS_COLORS[task.status]
        assert node.label == TYPE_LABELS[task.task_type]
        assert node.target == task.target
        expected = {
            frozenset({PlatformKind.UAV}): UAV_MARKER,
            frozenset({PlatformKind.UGV}): UGV_MARKER,
        }.get(task.eligible_platforms, MIXED_MARKER)
        assert node.marker == expected


def test_a_status_change_moves_only_the_colour(graph):
    before = {node.task_id: node for node in dag_render_spec(graph).nodes}
    target = sorted(graph.ids_with_status(TaskStatus.READY))[0]
    graph[target].status = TaskStatus.RUNNING

    after = {node.task_id: node for node in dag_render_spec(graph).nodes}
    assert after[target].color == STATUS_COLORS[TaskStatus.RUNNING]
    assert (after[target].x, after[target].y) == (before[target].x, before[target].y)
    assert {k: (v.x, v.y) for k, v in after.items()} == {
        k: (v.x, v.y) for k, v in before.items()
    }


# -- layout ---------------------------------------------------------------


def test_no_two_nodes_share_a_cell(graph):
    spec = dag_render_spec(graph)
    coordinates = [(node.x, node.y) for node in spec.nodes]
    assert len(set(coordinates)) == len(coordinates)


def test_rows_are_targets_and_columns_are_workflow_steps(graph):
    spec = dag_render_spec(graph)
    rows = {node.target: node.y for node in spec.nodes}
    # one row per target, and every node of a target sits on it
    for node in spec.nodes:
        assert node.y == rows[node.target]
    # zone recon rows come before incident rows, and each chain advances right
    assert spec.row_labels[:4] == ("ZONE_A", "ZONE_B", "ZONE_C", "ZONE_D")
    assert spec.row_labels[4:] == ("FIRE_SITE_1", "FIRE_SITE_2")
    chain = [n for n in spec.nodes if n.target == "FIRE_SITE_1"]
    assert sorted(n.x for n in chain) == [0.0, 1.0]


def test_incident_rows_sort_naturally_not_lexicographically(scene):
    # FIRE_SITE_10 must not sort ahead of FIRE_SITE_2 and make the figure lie.
    for _ in range(9):
        scene, _ = register_incident(scene, "ZONE_A")
    assert "FIRE_SITE_10" in scene.incidents

    from core.mission_state import MissionState
    from scenarios.compiler import compile_reference_graph

    specs = [(TaskType.GROUND_INSPECTION, iid) for iid in scene.incidents]
    built = compile_reference_graph(scene, specs, [])
    spec = dag_render_spec(MissionState(built, {}).graph)
    assert spec.row_labels[-3:] == ("FIRE_SITE_9", "FIRE_SITE_10", "FIRE_SITE_11")


# -- determinism ----------------------------------------------------------


def test_the_same_graph_always_yields_the_same_spec(graph):
    assert dag_render_spec(graph) == dag_render_spec(graph)


def test_the_spec_does_not_depend_on_task_insertion_order(graph):
    from core.task_graph import TaskGraph

    shuffled = TaskGraph()
    for task in sorted(graph.tasks, key=lambda t: t.task_id, reverse=True):
        shuffled.add_task(task)
    for pred, succ in sorted(graph.edges, reverse=True):
        shuffled.add_edge(pred, succ)

    assert dag_render_spec(shuffled) == dag_render_spec(graph)


def test_gids_are_the_task_and_edge_identities(graph):
    spec = dag_render_spec(graph)
    assert {node.gid for node in spec.nodes} == {task.task_id for task in graph.tasks}
    assert {edge.gid for edge in spec.edges} == {
        f"{pred}->{succ}" for pred, succ in graph.edges
    }


# -- purity and online updates --------------------------------------------


def test_rendering_leaves_the_session_state_untouched(scene, graph):
    state = fresh_session_state(graph, scene)
    before = (pre_state_hash(state), scene_hash(scene))

    dag_render_spec(state.graph)

    assert (pre_state_hash(state), scene_hash(scene)) == before


def test_an_online_update_adds_a_row_and_its_tasks_to_the_next_spec(scene, graph):
    state = fresh_session_state(graph, scene)
    before = dag_render_spec(state.graph)

    updated_scene, incident_id = register_incident(scene, "ZONE_A")
    plan = build_chain_patch(state.graph, incident_id, "GROUND_SUPPRESSION")
    committed, result = apply_patch(state, plan.patch, updated_scene)
    assert result.accepted

    after = dag_render_spec(committed.graph)

    # the new incident becomes its own row, and its whole chain is drawn
    assert incident_id not in before.row_labels
    assert incident_id in after.row_labels
    assert after.task_ids - before.task_ids == set(result.added_tasks)
    assert after.edge_keys == committed.graph.edges
    assert len(after.nodes) == len(before.nodes) + len(result.added_tasks)


def test_the_target_order_is_total_even_when_natural_keys_collide():
    # int() parsing makes these two natural keys equal; the raw string breaks
    # the tie so no two distinct ids ever compare the same (D-044 determinism).
    assert _natural_key("FIRE_SITE_2") == _natural_key("FIRE_SITE_02")
    assert _sort_key("FIRE_SITE_2") != _sort_key("FIRE_SITE_02")


def test_row_order_does_not_depend_on_the_hash_seed():
    """Targets are collected into a set, so a key tie would hand row order to
    set iteration — and therefore to PYTHONHASHSEED. Pinned across seeds."""
    probe = (
        "import dataclasses;"
        "from core.enums import TaskType;"
        "from demo.visualization import dag_render_spec;"
        "from scenarios.compiler import compile_reference_graph;"
        "from scenarios.scene import load_scene;"
        "s=load_scene('scenarios/industrial_park.yaml');"
        "i=dict(s.incidents);"
        "i['FIRE_SITE_02']=dataclasses.replace(i['FIRE_SITE_2'],incident_id='FIRE_SITE_02');"
        "s=dataclasses.replace(s,incidents=i);"
        "g=compile_reference_graph(s,[(TaskType.GROUND_INSPECTION,x) "
        "for x in ('FIRE_SITE_2','FIRE_SITE_02')],[]);"
        "print(dag_render_spec(g).row_labels)"
    )
    root = Path(__file__).parents[1]
    seen = set()
    for seed in ("0", "1", "2", "12345", "99999"):
        done = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        seen.add(done.stdout.strip())
    assert len(seen) == 1, f"row order varies with PYTHONHASHSEED: {seen}"


# -- P8.5b: drawing (§18.14) ---------------------------------------------


@pytest.fixture
def rendered(graph):
    from demo.visualization import render_task_graph

    spec = dag_render_spec(graph)
    figure = render_task_graph(spec)
    yield spec, figure
    figure.clear()


def _gids(figure) -> set[str]:
    return {
        artist.get_gid()
        for artist in figure.axes[0].get_children()
        if artist.get_gid()
    }


def test_the_spec_is_the_only_data_input():
    """A hand-built spec with no graph behind it must render, which is what
    proves the figure never reaches back to a TaskGraph or Scene."""
    from demo.visualization import DagEdgeSpec, DagNodeSpec, DagRenderSpec, render_task_graph

    invented = DagRenderSpec(
        nodes=(
            DagNodeSpec("A", "ALPHA", "ROW", 0.0, 0.0, "#123456", "o", TaskStatus.READY),
            DagNodeSpec("B", "BETA", "ROW", 1.0, 0.0, "#654321", "s", TaskStatus.RUNNING),
        ),
        edges=(DagEdgeSpec("A", "B"),),
        row_labels=("ROW",),
        columns=((0.0, "ALPHA"), (1.0, "BETA")),
    )
    figure = render_task_graph(invented)
    try:
        assert _gids(figure) == {"A", "B", "A->B"}
    finally:
        figure.clear()


def test_every_node_and_edge_becomes_an_identified_artist(rendered):
    spec, figure = rendered
    expected = {node.gid for node in spec.nodes} | {edge.gid for edge in spec.edges}
    assert _gids(figure) == expected
    assert len(expected) == len(spec.nodes) + len(spec.edges)


def test_node_artists_sit_at_the_spec_coordinates(rendered):
    spec, figure = rendered
    drawn = {
        artist.get_gid(): artist
        for artist in figure.axes[0].get_lines()
        if artist.get_gid()
    }
    for node in spec.nodes:
        xs, ys = drawn[node.task_id].get_data()
        assert (float(xs[0]), float(ys[0])) == (node.x, node.y)
        assert drawn[node.task_id].get_marker() == node.marker


def test_axis_labels_come_from_the_spec(rendered):
    spec, figure = rendered
    ax = figure.axes[0]
    assert [t.get_text() for t in ax.get_yticklabels()] == list(spec.row_labels)
    assert [t.get_text() for t in ax.get_xticklabels()] == [c[1] for c in spec.columns]
    assert list(ax.get_xticks()) == [c[0] for c in spec.columns]


def test_status_and_platform_legends_are_separate(rendered):
    _, figure = rendered
    ax = figure.axes[0]
    legends = [ax.get_legend()] + [
        child for child in ax.get_children()
        if child is not ax.get_legend() and type(child).__name__ == "Legend"
    ]
    titles = {legend.get_title().get_text() for legend in legends}
    assert titles == {"TaskStatus", "Platform"}

    by_title = {legend.get_title().get_text(): legend for legend in legends}
    status_labels = [t.get_text() for t in by_title["TaskStatus"].get_texts()]
    assert set(status_labels) == {status.value for status in TaskStatus}
    platform_labels = [t.get_text() for t in by_title["Platform"].get_texts()]
    assert platform_labels == ["UAV", "UGV", "UAV/UGV"]


def test_an_empty_graph_renders_without_raising():
    from core.task_graph import TaskGraph
    from demo.visualization import render_task_graph

    figure = render_task_graph(dag_render_spec(TaskGraph()))
    try:
        assert _gids(figure) == set()
        assert figure.axes
    finally:
        figure.clear()


def test_figure_height_grows_with_rows_but_is_bounded():
    from demo.visualization import MAX_HEIGHT_IN, MIN_HEIGHT_IN, figure_height

    assert figure_height(0) == MIN_HEIGHT_IN
    assert figure_height(6) > figure_height(2)
    assert figure_height(500) == MAX_HEIGHT_IN


def test_a_large_scene_stays_within_the_height_cap(scene):
    from core.mission_state import MissionState
    from demo.visualization import MAX_HEIGHT_IN, render_task_graph
    from scenarios.compiler import compile_reference_graph

    for _ in range(40):
        scene, _ = register_incident(scene, "ZONE_A")
    built = compile_reference_graph(
        scene, [(TaskType.GROUND_INSPECTION, iid) for iid in scene.incidents], []
    )
    figure = render_task_graph(dag_render_spec(MissionState(built, {}).graph))
    try:
        assert figure.get_size_inches()[1] == pytest.approx(MAX_HEIGHT_IN)
    finally:
        figure.clear()


def test_rendering_does_not_mutate_the_spec(rendered):
    spec, _ = rendered
    assert spec == dag_render_spec(load_reference_fixture().graph)


def test_rendering_is_headless_and_saves(rendered, tmp_path):
    _, figure = rendered
    out = tmp_path / "dag.png"
    figure.savefig(out)                       # no display, no pyplot backend
    assert out.stat().st_size > 0
    assert type(figure.canvas).__name__ == "FigureCanvasAgg"


# -- P8.5e: 2D mission map spec (§18.14, D-044) --------------------------


@pytest.fixture
def fixture_scene():
    return load_reference_fixture().scene


@pytest.fixture
def planned(fixture_scene, graph):
    from allocation.allocate import allocate

    state = fresh_session_state(graph, fixture_scene)
    return state, allocate(state, fixture_scene)


@pytest.fixture
def paused(fixture_scene, graph):
    from execution.executor import SimExecutor

    executor = SimExecutor(fresh_session_state(graph, fixture_scene), fixture_scene)
    for _ in range(5):
        executor.advance_to_next_completion()
    return executor


@pytest.fixture
def finished(fixture_scene, graph):
    from execution.executor import SimExecutor

    return SimExecutor(fresh_session_state(graph, fixture_scene), fixture_scene).run()


def test_all_three_builders_draw_the_same_scene_background(
    fixture_scene, graph, planned, paused, finished
):
    from demo.visualization import execution_map_spec, plan_map_spec, runtime_map_spec

    state, plan = planned
    specs = [
        plan_map_spec(fixture_scene, state.graph, plan),
        runtime_map_spec(fixture_scene, paused),
        execution_map_spec(fixture_scene, graph, finished),
    ]
    backgrounds = {(s.zones, s.incidents, s.route_lanes) for s in specs}
    assert len(backgrounds) == 1
    assert {s.mode for s in specs} == {"plan", "runtime", "execution"}


def test_agent_colours_are_the_same_in_every_mode(
    fixture_scene, graph, planned, paused, finished
):
    from demo.visualization import execution_map_spec, plan_map_spec, runtime_map_spec

    state, plan = planned
    colours = [
        {a.agent_id: a.color for a in spec.agents}
        for spec in (
            plan_map_spec(fixture_scene, state.graph, plan),
            runtime_map_spec(fixture_scene, paused),
            execution_map_spec(fixture_scene, graph, finished),
        )
    ]
    assert colours[0] == colours[1] == colours[2]
    assert len(set(colours[0].values())) == len(colours[0]), "colours must be distinct"


def test_map_specs_are_deterministic(fixture_scene, graph, planned, paused, finished):
    from demo.visualization import execution_map_spec, plan_map_spec, runtime_map_spec

    state, plan = planned
    assert plan_map_spec(fixture_scene, state.graph, plan) == plan_map_spec(
        fixture_scene, state.graph, plan
    )
    assert runtime_map_spec(fixture_scene, paused) == runtime_map_spec(
        fixture_scene, paused
    )
    assert execution_map_spec(fixture_scene, graph, finished) == execution_map_spec(
        fixture_scene, graph, finished
    )


def test_plan_legs_follow_task_start_order(fixture_scene, planned):
    from demo.visualization import plan_map_spec

    state, plan = planned
    spec = plan_map_spec(fixture_scene, state.graph, plan)
    for agent_id in {leg.agent_id for leg in spec.legs}:
        legs = sorted(
            (leg for leg in spec.legs if leg.agent_id == agent_id),
            key=lambda leg: leg.order,
        )
        starts = [plan.task_start[leg.task_id] for leg in legs]
        assert starts == sorted(starts), "a plan route must follow task_start"
        assert all(leg.phase == "planned" for leg in legs)


def test_execution_legs_follow_departure_order_not_task_id(
    fixture_scene, graph, finished
):
    from demo.visualization import execution_map_spec

    spec = execution_map_spec(fixture_scene, graph, finished)
    for agent_id in {leg.agent_id for leg in spec.legs}:
        legs = sorted(
            (leg for leg in spec.legs if leg.agent_id == agent_id),
            key=lambda leg: leg.order,
        )
        departures = [finished.task_departure[leg.task_id] for leg in legs]
        assert departures == sorted(departures)
    # only tasks that actually departed are drawn
    assert {leg.task_id for leg in spec.legs} <= set(finished.task_departure)


def test_uav_legs_are_two_point_straight_hops(fixture_scene, graph, finished):
    from demo.visualization import execution_map_spec

    spec = execution_map_spec(fixture_scene, graph, finished)
    uav_ids = {
        a.agent_id for a in spec.agents if a.platform_kind is PlatformKind.UAV
    }
    uav_legs = [leg for leg in spec.legs if leg.agent_id in uav_ids]
    assert uav_legs
    for leg in uav_legs:
        assert len(leg.points) == 2, "UAV travel is Euclidean (§8)"
        assert leg.points[1] == tuple(graph[leg.task_id].position)


def test_ugv_legs_follow_the_route_graph_and_match_its_distance(
    fixture_scene, graph, finished
):
    import math

    from demo.visualization import execution_map_spec

    spec = execution_map_spec(fixture_scene, graph, finished)
    route = fixture_scene.route_graph
    ugv_ids = {
        a.agent_id for a in spec.agents if a.platform_kind is PlatformKind.UGV
    }
    ugv_legs = [leg for leg in spec.legs if leg.agent_id in ugv_ids]
    assert ugv_legs

    positions = {route.position(node): node for node in route.nodes}
    for leg in ugv_legs:
        nodes = [positions[point] for point in leg.points]   # every point is a node
        assert tuple(nodes) == route.shortest_path_nodes(nodes[0], nodes[-1])
        drawn = sum(
            math.dist(a, b)
            for a, b in zip(leg.points, leg.points[1:], strict=False)
        )
        lane_total = route.shortest_path_distance(nodes[0], nodes[-1])
        assert drawn == pytest.approx(lane_total)


def test_a_paused_run_marks_the_running_leg_as_in_progress(fixture_scene, paused):
    from demo.visualization import runtime_map_spec

    spec = runtime_map_spec(fixture_scene, paused)
    running = {
        agent_id: state.current
        for agent_id, state in paused.sim.items()
        if state.current is not None
    }
    assert running, "the fixture must pause with work in flight"

    in_progress = {leg.agent_id: leg for leg in spec.legs if leg.phase == "in_progress"}
    assert set(in_progress) == set(running)
    for agent_id, leg in in_progress.items():
        assert leg.task_id == running[agent_id]
        assert leg.linestyle == "dashed"


def test_a_paused_agent_sits_at_its_last_confirmed_position(fixture_scene, paused):
    from demo.visualization import runtime_map_spec

    spec = runtime_map_spec(fixture_scene, paused)
    drawn = {agent.agent_id: agent.position for agent in spec.agents}
    route = fixture_scene.route_graph
    for agent_id, agent in paused.agents.items():
        if agent.platform_kind is PlatformKind.UAV:
            expected = tuple(agent.position)
        else:
            expected = tuple(route.position(paused.access_nodes[agent_id]))
        # Exactly the confirmed point — no pose is interpolated (D-044).
        assert drawn[agent_id] == expected

    for leg in spec.legs:
        if leg.phase == "in_progress":
            assert leg.points[0] == drawn[leg.agent_id]


def test_remaining_assignments_keep_the_agent_path_order(fixture_scene, paused):
    from demo.visualization import runtime_map_spec

    spec = runtime_map_spec(fixture_scene, paused)
    for agent_id, agent in paused.agents.items():
        running = paused.sim[agent_id].current
        expected = [task for task in agent.path if task != running]
        drawn = [
            leg.task_id
            for leg in sorted(
                (x for x in spec.legs if x.agent_id == agent_id and x.phase == "remaining"),
                key=lambda leg: leg.order,
            )
        ]
        assert drawn == expected


def test_leg_gids_are_unique_and_carry_their_identity(fixture_scene, paused):
    from demo.visualization import runtime_map_spec

    spec = runtime_map_spec(fixture_scene, paused)
    gids = [leg.gid for leg in spec.legs]
    assert len(set(gids)) == len(gids)
    for leg in spec.legs:
        assert leg.gid == f"{leg.agent_id}:{leg.order}:{leg.phase}:{leg.task_id}"


def test_building_a_runtime_map_does_not_touch_the_executor(fixture_scene, paused):
    from demo.visualization import runtime_map_spec
    from validator.hashing import pre_state_hash

    before = (pre_state_hash(paused.work), paused.now, scene_hash(fixture_scene))

    runtime_map_spec(fixture_scene, paused)

    assert (pre_state_hash(paused.work), paused.now, scene_hash(fixture_scene)) == before


# -- P8.5f: drawing the map (§18.14) -------------------------------------


def _hand_built_map(mode="execution", legs=None):
    from demo.visualization import (
        AgentMapSpec,
        MapLegSpec,
        MapPointSpec,
        MapRenderSpec,
    )

    return MapRenderSpec(
        mode=mode,
        zones=(MapPointSpec("Z1", 0.0, 0.0, "zone", "Zone One"),),
        incidents=(MapPointSpec("F1", 10.0, 10.0, "incident", "F1"),),
        route_lanes=(((0.0, 0.0), (10.0, 0.0)),),
        agents=(
            AgentMapSpec("A1", PlatformKind.UAV, "#111111", (0.0, 0.0)),
            AgentMapSpec("A2", PlatformKind.UGV, "#222222", (10.0, 0.0)),
        ),
        task_points=(MapPointSpec("T1", 10.0, 10.0, "task", "INSPECT"),),
        legs=(
            (MapLegSpec("A1", "T1", 0, ((0.0, 0.0), (10.0, 10.0)), "completed"),)
            if legs is None
            else legs
        ),
        simulation_time=12.5,
    )


def _map_gids(figure) -> set[str]:
    return {
        artist.get_gid()
        for artist in figure.axes[0].get_children()
        if artist.get_gid()
    }


def test_the_map_renderer_consumes_only_the_spec():
    from demo.visualization import render_mission_map

    figure = render_mission_map(_hand_built_map())
    try:
        assert _map_gids(figure) == {"A1:0:completed:T1"}
    finally:
        figure.clear()


def test_minimal_style_keeps_the_legs_but_drops_the_scene_backdrop():
    from demo.visualization import render_mission_map

    spec = _hand_built_map()
    full = render_mission_map(spec)
    minimal = render_mission_map(spec, minimal=True)
    try:
        # the assignment polyline (the gid'd artist) survives either way
        assert _map_gids(minimal) == _map_gids(full) == {"A1:0:completed:T1"}
        # minimal has no route-lane / zone / incident legend, so fewer legends
        assert len(minimal.axes[0].get_legend().get_texts()) <= len(
            full.axes[0].get_legend().get_texts()
        )
        assert len(minimal.axes[0].artists) < len(full.axes[0].artists)
    finally:
        full.clear()
        minimal.clear()


@pytest.mark.parametrize("mode", ["plan", "runtime", "execution"])
def test_each_mode_gets_its_own_title(mode):
    from demo.visualization import MAP_MODE_TITLES, render_mission_map

    figure = render_mission_map(_hand_built_map(mode=mode))
    try:
        title = figure.axes[0].get_title(loc="left")
        assert MAP_MODE_TITLES[mode] in title
        assert "12.5 s" in title
        # the three views are never overlaid — one map states one moment
        assert sum(other in title for other in MAP_MODE_TITLES.values()) == 1
    finally:
        figure.clear()


def test_every_leg_becomes_an_identified_artist(fixture_scene, graph, finished):
    from demo.visualization import execution_map_spec, render_mission_map

    spec = execution_map_spec(fixture_scene, graph, finished)
    figure = render_mission_map(spec)
    try:
        # Every leg, not only the ones long enough to be a line: a zero-distance
        # hop is still work performed and must not vanish from the map.
        assert _map_gids(figure) == {leg.gid for leg in spec.legs}
    finally:
        figure.clear()


def test_a_zero_distance_task_is_still_drawn_and_numbered(
    fixture_scene, graph, finished
):
    """A UGV suppressing where it just inspected travels no distance.

    Both GROUND_SUPPRESSION tasks in the reference run are like this. Skipping
    them dropped two of twelve tasks off the map, so the picture could not show
    that the workflow ever completed (§18.14).
    """
    from demo.visualization import execution_map_spec, render_mission_map

    spec = execution_map_spec(fixture_scene, graph, finished)
    zero_length = [leg for leg in spec.legs if len(leg.points) == 1]
    assert {leg.task_id for leg in zero_length} == {
        "GROUND_SUPPRESSION__FIRE_SITE_1",
        "GROUND_SUPPRESSION__FIRE_SITE_2",
    }

    figure = render_mission_map(spec)
    try:
        assert {leg.gid for leg in zero_length} <= _map_gids(figure)
        numbers = {t.get_text() for t in figure.axes[0].texts}
        for leg in zero_length:
            assert str(leg.order + 1) in numbers
    finally:
        figure.clear()


def test_order_numbers_at_a_shared_point_are_stacked_deterministically():
    from demo.visualization import MapLegSpec, render_mission_map

    shared = ((5.0, 5.0),)
    legs = (
        MapLegSpec("A2", "T1", 0, shared, "completed"),
        MapLegSpec("A2", "T2", 1, shared, "completed"),
    )
    offsets = []
    for _ in range(2):
        figure = render_mission_map(_hand_built_map(legs=legs))
        try:
            offsets.append(
                [
                    (t.get_text(), t.xyann)
                    for t in figure.axes[0].texts
                    if t.get_text() in {"1", "2"}
                ]
            )
        finally:
            figure.clear()
    assert offsets[0] == offsets[1]                       # deterministic
    assert len({offset for _, offset in offsets[0]}) == 2  # and not overlapping


def test_leg_lines_use_the_agent_colour_and_phase_style(fixture_scene, paused):
    from demo.visualization import LEG_LINESTYLES, render_mission_map, runtime_map_spec

    spec = runtime_map_spec(fixture_scene, paused)
    colors = {agent.agent_id: agent.color for agent in spec.agents}
    figure = render_mission_map(spec)
    try:
        lines = {line.get_gid(): line for line in figure.axes[0].get_lines() if line.get_gid()}
        for leg in spec.legs:
            if len(leg.points) < 2:
                continue
            line = lines[leg.gid]
            assert line.get_color() == colors[leg.agent_id]
            assert line.get_linestyle() == {
                "solid": "-", "dashed": "--", "dotted": ":",
            }[LEG_LINESTYLES[leg.phase]]
            assert [tuple(p) for p in zip(*line.get_data(), strict=False)] == list(leg.points)
    finally:
        figure.clear()


def test_the_leg_legend_lists_only_the_phases_present(fixture_scene, paused):
    from demo.visualization import render_mission_map, runtime_map_spec

    spec = runtime_map_spec(fixture_scene, paused)
    figure = render_mission_map(spec)
    try:
        ax = figure.axes[0]
        legends = [ax.get_legend()] + [
            child for child in ax.get_children()
            if child is not ax.get_legend() and type(child).__name__ == "Legend"
        ]
        by_title = {legend.get_title().get_text(): legend for legend in legends}
        assert set(by_title) == {"Agents", "Leg", "Map"}
        listed = {t.get_text() for t in by_title["Leg"].get_texts()}
        assert listed == {leg.phase for leg in spec.legs}
        # the background markers are explained rather than left to be guessed
        assert {t.get_text() for t in by_title["Map"].get_texts()} == {
            "Zone", "Incident", "Task", "Route lane",
        }
    finally:
        figure.clear()


def test_task_order_numbers_are_drawn(fixture_scene, graph, finished):
    from demo.visualization import execution_map_spec, render_mission_map

    spec = execution_map_spec(fixture_scene, graph, finished)
    figure = render_mission_map(spec)
    try:
        texts = {t.get_text() for t in figure.axes[0].texts}
        for leg in spec.legs:
            if len(leg.points) >= 2:
                assert str(leg.order + 1) in texts
    finally:
        figure.clear()


def test_the_map_uses_an_equal_aspect_with_padding():
    from demo.visualization import render_mission_map

    spec = _hand_built_map()
    figure = render_mission_map(spec)
    try:
        ax = figure.axes[0]
        assert ax.get_aspect() == 1.0                      # axis("equal")
        left, right = ax.get_xlim()
        assert left < 0.0 and right > 10.0                 # padded past the extent
    finally:
        figure.clear()


def test_degenerate_legs_do_not_raise():
    from demo.visualization import MapLegSpec, render_mission_map

    # A UGV already standing on its target node yields a one-point "leg" — it
    # still gets an artist and a gid. A spec with no legs at all happens before
    # anything is assigned and simply draws none.
    single = (MapLegSpec("A2", "T1", 0, ((10.0, 0.0),), "remaining"),)
    figure = render_mission_map(_hand_built_map(legs=single))
    try:
        assert _map_gids(figure) == {single[0].gid}
    finally:
        figure.clear()

    figure = render_mission_map(_hand_built_map(legs=()))
    try:
        assert _map_gids(figure) == set()
        assert figure.axes
    finally:
        figure.clear()


def test_rendering_the_map_does_not_mutate_the_spec(fixture_scene, graph, finished):
    from demo.visualization import execution_map_spec, render_mission_map

    spec = execution_map_spec(fixture_scene, graph, finished)
    figure = render_mission_map(spec)
    try:
        assert spec == execution_map_spec(fixture_scene, graph, finished)
    finally:
        figure.clear()


@pytest.mark.parametrize("suffix", ["png", "pdf"])
def test_the_map_saves_headless(tmp_path, suffix):
    from demo.visualization import render_mission_map

    figure = render_mission_map(_hand_built_map())
    try:
        assert type(figure.canvas).__name__ == "FigureCanvasAgg"
        out = tmp_path / f"map.{suffix}"
        figure.savefig(out)
        assert out.stat().st_size > 0
    finally:
        figure.clear()


def test_an_unfinished_run_is_refused_by_the_execution_map(fixture_scene, graph):
    """DEADLOCK/STEP_LIMIT departures never arrived (§18.14).

    Drawing them would put agents on targets they never reached, under a title
    saying the run completed. There is no map mode for an abandoned run, so
    refusing is honest where guessing is not.
    """
    import dataclasses

    from demo.visualization import execution_map_spec
    from execution.executor import SimExecutor, Termination

    result = SimExecutor(
        fresh_session_state(graph, fixture_scene), fixture_scene
    ).run()
    for termination in (Termination.DEADLOCK, Termination.STEP_LIMIT):
        unfinished = dataclasses.replace(result, termination=termination)
        with pytest.raises(ValueError, match="COMPLETED"):
            execution_map_spec(fixture_scene, graph, unfinished)
