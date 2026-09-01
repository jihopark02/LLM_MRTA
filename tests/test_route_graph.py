"""Unit tests for RouteGraph (RESEARCH_CONTRACT.md §8). P1 gate items 1, 5."""

import math

import pytest

from core.route_graph import RouteGraph


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
