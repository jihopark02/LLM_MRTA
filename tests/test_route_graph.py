"""Unit tests for RouteGraph (RESEARCH_CONTRACT.md §8). P1 gate items 1, 5."""

import math
from pathlib import Path

import pytest

from core.route_graph import RouteGraph

SCENARIOS = Path(__file__).parents[1] / "scenarios"


def line_graph() -> RouteGraph:
    g = RouteGraph()
    g.add_node("N0", (0.0, 0.0))
    g.add_node("N1", (10.0, 0.0))
    g.add_node("N2", (10.0, 10.0))
    g.add_lane("N0", "N1")
    g.add_lane("N1", "N2")
    return g


def test_duplicate_node_rejected():
    g = RouteGraph()
    g.add_node("N0", (0.0, 0.0))
    with pytest.raises(ValueError):
        g.add_node("N0", (1.0, 1.0))


def test_lane_endpoint_must_be_a_node():
    g = RouteGraph()
    g.add_node("N0", (0.0, 0.0))
    with pytest.raises(KeyError):
        g.add_lane("N0", "N9")


def test_lane_default_weight_is_euclidean():
    g = line_graph()
    assert g.shortest_path_distance("N0", "N1") == pytest.approx(10.0)
    assert g.shortest_path_distance("N0", "N2") == pytest.approx(20.0)


@pytest.mark.parametrize("bad", [-1.0, 0.0, float("nan"), float("inf")])
def test_non_positive_or_non_finite_weight_is_rejected(bad):
    g = RouteGraph()
    g.add_node("A", (0.0, 0.0))
    g.add_node("B", (1.0, 0.0))
    with pytest.raises(ValueError):
        g.add_lane("A", "B", weight=bad)


def test_explicit_weight_overrides_geometry():
    g = RouteGraph()
    g.add_node("A", (0.0, 0.0))
    g.add_node("B", (100.0, 0.0))
    g.add_lane("A", "B", weight=3.0)
    assert g.shortest_path_distance("A", "B") == 3.0


def test_shortest_path_prefers_cheaper_route():
    g = line_graph()
    g.add_lane("N0", "N2", weight=5.0)  # shortcut
    assert g.shortest_path_distance("N0", "N2") == 5.0


def test_unreachable_returns_none():
    g = line_graph()
    g.add_node("ISO", (50.0, 50.0))
    assert g.shortest_path_distance("N0", "ISO") is None
    assert not g.is_reachable("N0", "ISO")


def test_same_node_distance_zero():
    g = line_graph()
    assert g.shortest_path_distance("N1", "N1") == 0.0


def test_unknown_node_raises():
    g = line_graph()
    with pytest.raises(KeyError):
        g.shortest_path_distance("N0", "NOPE")


def test_diamond_graph_symmetry():
    g = RouteGraph()
    for i, pos in enumerate([(0, 0), (1, 1), (1, -1), (2, 0)]):
        g.add_node(f"D{i}", (float(pos[0]), float(pos[1])))
    g.add_lane("D0", "D1")
    g.add_lane("D0", "D2")
    g.add_lane("D1", "D3")
    g.add_lane("D2", "D3")
    d = g.shortest_path_distance("D0", "D3")
    assert d == pytest.approx(2 * math.sqrt(2))
    assert g.shortest_path_distance("D3", "D0") == pytest.approx(d)


# -- shortest_path_nodes (§18.14, D-044) ---------------------------------


def _diamond(reverse_lane_order: bool = False) -> RouteGraph:
    """Two equal-cost routes N0->N3, so the tie-break is observable."""
    g = RouteGraph()
    for node, pos in (
        ("N0", (0.0, 0.0)),
        ("NA", (5.0, 5.0)),
        ("NB", (5.0, -5.0)),
        ("N3", (10.0, 0.0)),
    ):
        g.add_node(node, pos)
    lanes = [("N0", "NA", 4.0), ("NA", "N3", 4.0), ("N0", "NB", 4.0), ("NB", "N3", 4.0)]
    for a, b, w in reversed(lanes) if reverse_lane_order else lanes:
        g.add_lane(a, b, w)
    return g


def test_path_endpoints_and_lanes_hold_for_every_pair():
    g = line_graph()
    lanes = {(a, b): w for a, b, w in g.lanes}
    for src in sorted(g.nodes):
        for dst in sorted(g.nodes):
            path = g.shortest_path_nodes(src, dst)
            distance = g.shortest_path_distance(src, dst)
            assert (path is None) == (distance is None)
            if path is None:
                continue
            assert path[0] == src and path[-1] == dst
            total = 0.0
            for a, b in zip(path, path[1:], strict=False):
                weight = lanes.get((a, b), lanes.get((b, a)))
                assert weight is not None, f"no lane between {a} and {b}"
                total += weight
            assert total == pytest.approx(distance)


def test_the_path_is_the_cheaper_route_not_merely_a_route():
    g = RouteGraph()
    for node, pos in (("A", (0.0, 0.0)), ("B", (1.0, 0.0)), ("C", (2.0, 0.0))):
        g.add_node(node, pos)
    g.add_lane("A", "C", 100.0)
    g.add_lane("A", "B", 1.0)
    g.add_lane("B", "C", 1.0)

    assert g.shortest_path_nodes("A", "C") == ("A", "B", "C")
    assert g.shortest_path_distance("A", "C") == pytest.approx(2.0)


def test_equal_cost_routes_break_ties_on_node_id_not_insertion_order():
    forward, reversed_order = _diamond(), _diamond(reverse_lane_order=True)

    assert forward.shortest_path_distance("N0", "N3") == pytest.approx(
        reversed_order.shortest_path_distance("N0", "N3")
    )
    # Same graph, lanes added in the opposite order: the drawn route must not
    # depend on that, or a figure would change without the scene changing.
    assert forward.shortest_path_nodes("N0", "N3") == reversed_order.shortest_path_nodes(
        "N0", "N3"
    )
    assert forward.shortest_path_nodes("N0", "N3") == ("N0", "NA", "N3")


def test_same_node_path_is_just_that_node():
    g = line_graph()
    assert g.shortest_path_nodes("N1", "N1") == ("N1",)
    assert g.shortest_path_distance("N1", "N1") == 0.0


def test_unreachable_path_is_none_like_the_distance():
    g = line_graph()
    g.add_node("ISLAND", (99.0, 99.0))
    assert g.shortest_path_nodes("N0", "ISLAND") is None
    assert g.shortest_path_distance("N0", "ISLAND") is None


@pytest.mark.parametrize(("src", "dst"), [("NOPE", "N1"), ("N1", "NOPE")])
def test_unknown_node_raises_for_both_queries(src, dst):
    g = line_graph()
    with pytest.raises(KeyError):
        g.shortest_path_nodes(src, dst)
    with pytest.raises(KeyError):
        g.shortest_path_distance(src, dst)


def test_querying_a_path_does_not_mutate_the_graph():
    g = _diamond()
    before = (g.nodes, g.lanes)

    g.shortest_path_nodes("N0", "N3")
    g.shortest_path_distance("N0", "N3")

    assert (g.nodes, g.lanes) == before


def test_the_two_queries_agree_on_the_scene_route_graph():
    from scenarios.scene import load_scene

    graph = load_scene(SCENARIOS / "industrial_park.yaml").route_graph
    lanes = {(a, b): w for a, b, w in graph.lanes}
    for src in sorted(graph.nodes):
        for dst in sorted(graph.nodes):
            path = graph.shortest_path_nodes(src, dst)
            assert path is not None
            total = sum(
                lanes.get((a, b), lanes.get((b, a)))
                for a, b in zip(path, path[1:], strict=False)
            )
            assert total == pytest.approx(graph.shortest_path_distance(src, dst))
