"""Canonical hashes for reproducibility records (RESEARCH_CONTRACT.md §14).

A validation result records ``graph_hash``, ``scene_hash`` and
``validator_version`` so that "same graph -> same verdict" is a checkable claim
against a fixed rule set.

A MissionPatch verdict needs two more (D-027): ``patch_hash`` identifies the
operations, and ``pre_state_hash`` identifies the state they were judged
against — the same graph and the same patch can be accepted, released or
rejected with E_RUNNING_LOCKED depending on the target task's status, so the
operation hash alone cannot reproduce a verdict.
"""

import hashlib
import json
import math

from core.enums import TaskType
from validator.candidate import TaskKey, key_str

# Validator rule-set version (RESEARCH_CONTRACT.md §14). Bump on any verdict-rule
# change: invariant added/removed/redefined, schema range change, hash format change.
#   1.0 -> 1.1 (D-008): unknown-field rejection, op field schema, assignment
#   invariant + referential integrity, priority 1..10, hash payload includes priority.
#   1.1 -> 1.2 (D-016): TaskType HAZARD_MARKER_DEPLOY -> GROUND_SUPPRESSION
#   (allowed set + workflow invariant meaning changed).
#   1.2 -> 1.3 (D-022): candidate task entry schema {task_type, target, priority}
#   -> {task_type, target}; priority is compiler-derived, still in the hash payload.
#   1.3 -> 1.4 (D-027): (i) MissionPatch AddTask op schema {task_type, target,
#   priority} -> {task_type, target}, priority derived by apply_patch;
#   (ii) scene_hash zone payload gains the operator-report response point
#   (position + access node, §18.10); (iii) patch_hash / pre_state_hash defined.
VALIDATOR_VERSION = "1.4"

# (task_type, target, priority) — priority is a CBBA execution input (D-007),
# scene-derived (D-022), and part of the audit hash.
HashNode = tuple[TaskType, str, int]


def _sha(payload: object) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def graph_hash(nodes: list[HashNode], edges: list[tuple[TaskKey, TaskKey]]) -> str:
    return _sha(
        {
            "nodes": sorted([tt.value, target, priority] for tt, target, priority in nodes),
            "edges": sorted([key_str(p), key_str(s)] for p, s in edges),
        }
    )


def scene_hash(scene) -> str:
    return _sha(
        {
            "scene_id": scene.scene_id,
            "zones": {
                zid: [
                    z.name,
                    list(z.recon_waypoint),
                    # §18.10: where an operator-reported incident in this zone
                    # lands. Part of the scene's meaning, so part of its hash.
                    list(z.reported_incident_position),
                    z.reported_incident_access_node,
                ]
                for zid, z in sorted(scene.zones.items())
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


# -- MissionPatch audit hashes (§14, D-027) ---------------------------------


def _canonical_op(op) -> list:
    """Stable identity of one already field-schema-valid operation.

    Dispatch on the type, not its name: a subclass passes the isinstance-based
    field-schema check, so a name comparison would read the wrong attributes.
    """
    from validator.patch import AddEdge, AddTask, RemoveEdge

    if isinstance(op, AddTask):
        return ["AddTask", op.task_type.value, op.target]
    if isinstance(op, AddEdge):
        return ["AddEdge", key_str(op.predecessor), key_str(op.successor)]
    if isinstance(op, RemoveEdge):
        return ["RemoveEdge", key_str(op.predecessor), key_str(op.successor)]
    raise ValueError(f"not a MissionPatch operation: {type(op).__name__}")


def patch_hash(
    base_graph_hash: str, pre_scene_hash: str, operations: list, validator_version: str
) -> str:
    """Identity of a patch's operations against a starting graph + scene.

    Only call this once the operations have passed the field-level schema check
    (``validate_patch_field_schema``) — a malformed op has no safe canonical
    serialization, and the audit record stores ``patch_hash = None`` for it.
    """
    return _sha(
        {
            "base_graph_hash": base_graph_hash,
            "pre_scene_hash": pre_scene_hash,
            "operations": sorted(_canonical_op(op) for op in operations),
            "validator_version": validator_version,
        }
    )


def _canonical_float(value: float, label: str) -> str:
    """Lossless, platform-stable float text. NaN/inf are not auditable values."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{label} must be a real number, got {value!r}")
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite, got {value!r}")
    return float(value).hex()


def pre_state_hash(state) -> str:
    """Identity of the MissionState a patch is judged against (D-027).

    ``bundle`` and ``path`` keep their order — they are CBBA execution order,
    so ``[A, B]`` and ``[B, A]`` are different states and must not collide.
    Only the agents themselves are sorted, by ``agent_id``.
    """
    return _sha(
        {
            # task_id is unique, so sort on it explicitly rather than relying on
            # list comparison never reaching the nullable assigned_agent.
            "tasks": sorted(
                ([t.task_id, t.status.value, t.assigned_agent] for t in state.graph.tasks),
                key=lambda row: row[0],
            ),
            "agents": [
                [
                    agent_key,                             # the dict key, and
                    state.agents[agent_key].agent_id,      # the Agent's own id:
                    # §10 rule 6 rejects a state where these disagree, so they
                    # must be separately auditable or two states with different
                    # verdicts would share a hash.
                    list(state.agents[agent_key].bundle),  # order is meaningful
                    list(state.agents[agent_key].path),    # order is meaningful
                    state.agents[agent_key].current_task,
                ]
                for agent_key in sorted(state.agents)
            ],
            "winning_bids": [
                [tid, _canonical_float(state.winning_bids[tid], f"winning_bids[{tid}]")]
                for tid in sorted(state.winning_bids)
            ],
        }
    )
