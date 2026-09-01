"""UGV route graph (RESEARCH_CONTRACT.md §8).

A predefined undirected lane/waypoint graph. UGV travel cost is the Dijkstra
shortest-path distance between named access nodes, divided by speed — arbitrary
coordinates are never fed to Dijkstra directly. At scene-load time every
UGV-targeted task location must be connected to this graph (P1 gate item 5); an
unreachable target means the scenario is rejected before allocation.
"""

import heapq
import math


class RouteGraph:
    def __init__(self) -> None:
        self._nodes: dict[str, tuple[float, float]] = {}
        self._adj: dict[str, dict[str, float]] = {}

    def add_node(self, node_id: str, position: tuple[float, float]) -> None:
        if node_id in self._nodes:
            raise ValueError(f"duplicate route node: {node_id}")
        self._nodes[node_id] = position
        self._adj.setdefault(node_id, {})

    def add_lane(self, a: str, b: str, weight: float | None = None) -> None:
        """Undirected lane. Weight defaults to Euclidean distance between nodes.

        The weight must be finite and strictly positive — Dijkstra is invalid
        with negative edges, and NaN/inf silently break shortest-path results.
        """
        for n in (a, b):
            if n not in self._nodes:
                raise KeyError(f"lane endpoint is not a route node: {n}")
        if a == b:
            raise ValueError(f"self-loop lane: {a}")
        w = weight if weight is not None else math.dist(self._nodes[a], self._nodes[b])
        if not math.isfinite(w) or w <= 0.0:
            raise ValueError(f"lane {a}-{b}: weight must be finite and positive, got {w!r}")
        self._adj[a][b] = w
        self._adj[b][a] = w

    def __contains__(self, node_id: str) -> bool:
        return node_id in self._nodes

    @property
    def nodes(self) -> set[str]:
        return set(self._nodes)

    @property
    def lanes(self) -> list[tuple[str, str, float]]:
        """Each undirected lane once, as (a, b, weight) with a < b."""
        return sorted(
            (a, b, w) for a, nbrs in self._adj.items() for b, w in nbrs.items() if a < b
        )

    def position(self, node_id: str) -> tuple[float, float]:
        return self._nodes[node_id]

    def shortest_path_distance(self, src: str, dst: str) -> float | None:
        if src not in self._nodes or dst not in self._nodes:
            raise KeyError(f"unknown route node: {src if src not in self._nodes else dst}")
        if src == dst:
            return 0.0
        dist: dict[str, float] = {src: 0.0}
        pq: list[tuple[float, str]] = [(0.0, src)]
        while pq:
            d, node = heapq.heappop(pq)
            if node == dst:
                return d
            if d > dist.get(node, math.inf):
                continue
            for nbr, w in self._adj[node].items():
                nd = d + w
                if nd < dist.get(nbr, math.inf):
                    dist[nbr] = nd
                    heapq.heappush(pq, (nd, nbr))
        return None

    def is_reachable(self, src: str, dst: str) -> bool:
        return self.shortest_path_distance(src, dst) is not None
