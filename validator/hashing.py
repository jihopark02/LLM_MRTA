"""Canonical hashes for reproducibility records (RESEARCH_CONTRACT.md §14).

A validation result records ``graph_hash``, ``scene_hash`` and
``validator_version`` so that "same graph -> same verdict" is a checkable claim
against a fixed rule set.
"""

import hashlib
import json

from validator.candidate import TaskKey, key_str

# Validator rule-set version. Bump when an invariant's meaning changes.
VALIDATOR_VERSION = "1.0"


def _sha(payload: object) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def graph_hash(nodes: list[TaskKey], edges: list[tuple[TaskKey, TaskKey]]) -> str:
    return _sha(
        {
            "nodes": sorted(key_str(n) for n in nodes),
            "edges": sorted([key_str(p), key_str(s)] for p, s in edges),
        }
    )


def scene_hash(scene) -> str:
    return _sha(
        {
            "scene_id": scene.scene_id,
            "zones": {
                zid: [z.name, list(z.recon_waypoint)] for zid, z in sorted(scene.zones.items())
            },
            "incidents": {
                iid: [i.zone, i.priority, list(i.position), i.access_node, i.status.value]
                for iid, i in sorted(scene.incidents.items())
            },
            "route_nodes": {
                n: list(scene.route_graph.position(n)) for n in sorted(scene.route_graph.nodes)
            },
            "route_lanes": [[a, b, w] for a, b, w in scene.route_graph.lanes],
            "fleet": sorted(
                [
                    a.agent_id,
                    a.platform_kind.value,
                    sorted(c.value for c in a.capabilities),
                    list(a.initial_position),
                    a.speed,
                ]
                for a in scene.fleet
            ),
            "agent_access_nodes": dict(sorted(scene.agent_access_nodes.items())),
        }
    )
