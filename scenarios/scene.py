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
    # Where an operator-reported incident in this zone is placed (§18.10).
    # Fixed in the scene so the LLM never invents coordinates: the UAV target
    # position and the UGV route node are both predefined per zone.
    reported_incident_position: tuple[float, float]
    reported_incident_access_node: str


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


def _finite_xy(pair, label: str) -> tuple[float, float]:
    """A coordinate that will become a task target must be a real point.

    Only the §18.10 response point is checked here — the older coordinate
    fields (recon_waypoint, incident position, route nodes) still go through
    the unchecked ``_xy`` and are left as they are.
    """
    xy = _xy(pair)
    if not all(math.isfinite(v) for v in xy):
        raise ValueError(f"{label} must be two finite numbers, got {pair!r}")
    return xy


def _positive_finite(value: float, label: str) -> float:
    v = float(value)
    if not math.isfinite(v) or v <= 0.0:
        raise ValueError(f"{label} must be finite and positive, got {value!r}")
    return v


def _priority(value: object, label: str) -> int:
    # The scene is the source of truth for priority (§7, D-022); the compiler
    # trusts it, so the range check has to happen here, not be laundered by
    # int() coercion (bool is not accepted; "9" is not accepted).
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 10:
        raise ValueError(f"{label} must be an int in 1..10, got {value!r}")
    return value


def load_scene(path: str | Path) -> Scene:
    raw = yaml.safe_load(Path(path).read_text())

    zones = {
        zid: Zone(
            zone_id=zid,
            name=z["name"],
            recon_waypoint=_xy(z["recon_waypoint"]),
            reported_incident_position=_finite_xy(
                z["reported_incident_position"], f"{zid}.reported_incident_position"
            ),
            reported_incident_access_node=z["reported_incident_access_node"],
        )
        for zid, z in raw["zones"].items()
    }
    incidents = {
        iid: Incident(
            incident_id=iid,
            zone=i["zone"],
            priority=_priority(i["priority"], f"{iid}.priority"),
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

    # §18.10: an operator may report an incident in ANY zone, so every zone's
    # response access node must be a route node too. Reachability from the UGV
    # starts is checked below, once the fleet is loaded.
    for zone in zones.values():
        if zone.reported_incident_access_node not in rg:
            raise ValueError(
                f"{zone.zone_id}: reported_incident_access_node "
                f"{zone.reported_incident_access_node} not in route graph"
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

    scene = Scene(raw["scene_id"], zones, incidents, rg, fleet, access_nodes)

    # §18.10 + §8 (c): a reported incident in any zone must be able to receive
    # GROUND_INSPECTION / GROUND_SUPPRESSION, so its response node must be
    # reachable from every UGV start. Unlike the task-level check this needs no
    # task list, so it belongs at scene load.
    reach_errors = scene.reachability_errors(
        {f"{zid}.reported_incident": z.reported_incident_access_node for zid, z in zones.items()}
    )
    if reach_errors:
        raise ValueError(
            "zone response point reachability failed:\n  " + "\n  ".join(reach_errors)
        )
    return scene
