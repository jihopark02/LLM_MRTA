"""Semantic scene loader (RESEARCH_CONTRACT.md §3, §5, §8).

The scene is the environment + fleet vocabulary. Task instances are NOT here;
they are compiled against this scene by ``scenarios/compiler.py`` — for the
trusted reference fixture in P1, and (P5) for LLM output only after it has
passed the P2 whole-graph Validator.

UGV start nodes are kept in ``Scene.agent_access_nodes`` rather than on the core
``Agent`` (contract §6 keeps platform-specific config out of the core model);
the platform adapter design is settled in P7.
"""

import math
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from core.agent import Agent
from core.enums import Capability, IncidentStatus, PlatformKind
from core.route_graph import RouteGraph


@dataclass(slots=True)
class Zone:
    zone_id: str
    name: str
    recon_waypoint: tuple[float, float]


@dataclass(slots=True)
class Incident:
    incident_id: str
    zone: str
    priority: int
    position: tuple[float, float]
    access_node: str
    status: IncidentStatus


@dataclass(slots=True)
class Scene:
    scene_id: str
    zones: dict[str, Zone]
    incidents: dict[str, Incident]
    route_graph: RouteGraph
    fleet: list[Agent]
    agent_access_nodes: dict[str, str] = field(default_factory=dict)

    def eligible_agents(self, required_capabilities, eligible_platforms) -> list[Agent]:
        return [
            a
            for a in self.fleet
            if a.platform_kind in eligible_platforms
            and a.has_capabilities(required_capabilities)
        ]

    def reachability_errors(self, ugv_targets: dict[str, str]) -> list[str]:
        """Every UGV-targeted access node must be reachable from every UGV start
        node (contract §8, P1 gate item 5). ``ugv_targets`` maps task_id -> access_node.
        """
        errors: list[str] = []
        ugv_starts = {
            self.agent_access_nodes[a.agent_id]
            for a in self.fleet
            if a.platform_kind is PlatformKind.UGV
        }
        for task_id, node in sorted(ugv_targets.items()):
            if node not in self.route_graph:
                errors.append(f"{task_id}: access node {node} not in route graph")
                continue
            for start in sorted(ugv_starts):
                if not self.route_graph.is_reachable(start, node):
                    errors.append(f"{task_id}: {node} unreachable from UGV start {start}")
        return errors


def _xy(pair) -> tuple[float, float]:
    return (float(pair[0]), float(pair[1]))


def _positive_finite(value: float, label: str) -> float:
    v = float(value)
    if not math.isfinite(v) or v <= 0.0:
        raise ValueError(f"{label} must be finite and positive, got {value!r}")
    return v


def load_scene(path: str | Path) -> Scene:
    raw = yaml.safe_load(Path(path).read_text())

    zones = {
        zid: Zone(zid, z["name"], _xy(z["recon_waypoint"]))
        for zid, z in raw["zones"].items()
    }
    incidents = {
        iid: Incident(
            incident_id=iid,
            zone=i["zone"],
            priority=int(i["priority"]),
            position=_xy(i["position"]),
            access_node=i["access_node"],
            status=IncidentStatus(i["status"]),
        )
        for iid, i in raw["incidents"].items()
    }

    rg = RouteGraph()
    for node_id, pos in raw["route_graph"]["nodes"].items():
        rg.add_node(node_id, _xy(pos))
    for a, b in raw["route_graph"]["lanes"]:
        rg.add_lane(a, b)

    # Contract §8 (a): every incident's ground access node must be a route node,
    # so UGV-task reachability can be checked at fixture/candidate load.
    for incident in incidents.values():
        if incident.access_node not in rg:
            raise ValueError(
                f"{incident.incident_id}: access_node {incident.access_node} not in route graph"
            )

    fleet: list[Agent] = []
    access_nodes: dict[str, str] = {}
    seen_agent_ids: set[str] = set()
    for spec in raw["fleet"]:
        agent_id = spec["agent_id"]
        if agent_id in seen_agent_ids:  # §8 (d): agent_id is a dict key in CBBA
            raise ValueError(f"duplicate agent_id: {agent_id}")
        seen_agent_ids.add(agent_id)
        kind = PlatformKind(spec["platform_kind"])
        caps = frozenset(Capability(c) for c in spec["capabilities"])
        if kind is PlatformKind.UGV:
            node = spec["access_node"]
            if node not in rg:  # §8 (b)
                raise ValueError(f"{agent_id}: access_node {node} not in route graph")
            access_nodes[agent_id] = node
            pos = rg.position(node)
        else:
            pos = _xy(spec["position"])
        fleet.append(
            Agent(
                agent_id=agent_id,
                platform_kind=kind,
                capabilities=caps,
                initial_position=pos,
                position=pos,
                speed=_positive_finite(spec["speed"], f"{agent_id}.speed"),
            )
        )

    incident_zones = {i.zone for i in incidents.values()}
    unknown = incident_zones - set(zones)
    if unknown:
        raise ValueError(f"incident references unknown zone(s): {sorted(unknown)}")

    return Scene(raw["scene_id"], zones, incidents, rg, fleet, access_nodes)
