"""Deterministic whole-graph invariants (RESEARCH_CONTRACT.md §9).

These run on the FINAL candidate graph, from scratch, every time (§9
multi-transaction bypass note). The checks operate on an abstract view — a list
of task keys (task_type, target) plus a list of (predecessor, successor) key
pairs — so the same code serves both the LLM-pipeline candidate and a
post-patch TaskGraph.

Covered here: #4 (E_UNKNOWN_REF target), #5/#6 (edge endpoint / self-loop,
defensive), #8 (E_CYCLE), #9 (E_INFEASIBLE), #10 (E_WORKFLOW), #11
(E_CROSS_INCIDENT), #12 (E_UNREACHABLE). #1-3/#7 are raw-list checks
(validator/candidate.py). #13/#14 are patch-scoped (validator/patch.py).
"""

from collections import defaultdict, deque

from core.enums import PlatformKind, TaskType
from scenarios.compiler import TASK_TABLE
from scenarios.scene import Scene
from validator.candidate import TaskKey, key_str
from validator.errors import ErrorCode, ValidationError

_CHAIN_HEADS = frozenset({TaskType.AREA_RECON, TaskType.THERMAL_RECON})
WORKFLOW_PREDECESSOR: dict[TaskType, TaskType] = {
    TaskType.SUPPRESSANT_DROP: TaskType.THERMAL_RECON,
    TaskType.GROUND_INSPECTION: TaskType.SUPPRESSANT_DROP,
    TaskType.HAZARD_MARKER_DEPLOY: TaskType.GROUND_INSPECTION,
}
_Edge = tuple[TaskKey, TaskKey]


def _targets_incident(task_type: TaskType) -> bool:
    return TASK_TABLE[task_type].target_kind == "incident"


def _has_cycle(nodes: list[TaskKey], edges: list[_Edge]) -> bool:
    node_set = set(nodes)
    indeg = {n: 0 for n in node_set}
    adj: dict[TaskKey, list[TaskKey]] = defaultdict(list)
    for p, s in edges:
        if p in node_set and s in node_set:
            adj[p].append(s)
            indeg[s] += 1
    queue = deque(n for n, d in indeg.items() if d == 0)
    seen = 0
    while queue:
        n = queue.popleft()
        seen += 1
        for m in adj[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                queue.append(m)
    return seen != len(node_set)


def _workflow_errors(nodes: list[TaskKey], edges: list[_Edge]) -> list[ValidationError]:
    preds: dict[TaskKey, set[TaskKey]] = defaultdict(set)
    for p, s in edges:
        preds[s].add(p)
    errors: list[ValidationError] = []
    for node in nodes:
        task_type, target = node
        got = preds.get(node, set())
        if task_type in _CHAIN_HEADS:
            if got:
                have = sorted(key_str(g) for g in got)
                errors.append(
                    ValidationError(
                        ErrorCode.E_WORKFLOW,
                        key_str(node),
                        f"chain head must have no predecessor, has {have}",
                    )
                )
            continue
        want = {(WORKFLOW_PREDECESSOR[task_type], target)}
        if got != want:
            errors.append(
                ValidationError(
                    ErrorCode.E_WORKFLOW,
                    key_str(node),
                    f"expected exactly predecessor {key_str(next(iter(want)))}, "
                    f"got {sorted(key_str(g) for g in got)}",
                )
            )
    return errors


def _reachability_errors(nodes: list[TaskKey], scene: Scene) -> list[ValidationError]:
    ugv_targets = {
        key_str(node): scene.incidents[node[1]].access_node
        for node in nodes
        if PlatformKind.UGV in TASK_TABLE[node[0]].eligible_platforms
        and node[1] in scene.incidents
    }
    return [
        ValidationError(ErrorCode.E_UNREACHABLE, msg.split(":", 1)[0], msg)
        for msg in scene.reachability_errors(ugv_targets)
    ]


def validate_structure(
    nodes: list[TaskKey], edges: list[_Edge], scene: Scene
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    unique_nodes = list(dict.fromkeys(nodes))
    node_set = set(unique_nodes)

    for task_type, target in unique_nodes:
        kind = TASK_TABLE[task_type].target_kind
        pool = scene.zones if kind == "zone" else scene.incidents
        if target not in pool:
            errors.append(
                ValidationError(
                    ErrorCode.E_UNKNOWN_REF, key_str((task_type, target)), f"unknown {kind}"
                )
            )
        spec = TASK_TABLE[task_type]
        if not scene.eligible_agents(spec.required_capabilities, spec.eligible_platforms):
            errors.append(
                ValidationError(
                    ErrorCode.E_INFEASIBLE,
                    key_str((task_type, target)),
                    "no fleet agent satisfies capability + platform",
                )
            )

    for p, s in edges:
        if p == s:
            errors.append(ValidationError(ErrorCode.E_SELF_LOOP, key_str(p)))
        for endpoint in (p, s):
            if endpoint not in node_set:
                errors.append(
                    ValidationError(
                        ErrorCode.E_UNKNOWN_REF,
                        f"{key_str(p)} -> {key_str(s)}",
                        f"endpoint {key_str(endpoint)} is not a task",
                    )
                )
        if _targets_incident(p[0]) and _targets_incident(s[0]) and p[1] != s[1]:
            errors.append(
                ValidationError(
                    ErrorCode.E_CROSS_INCIDENT,
                    f"{key_str(p)} -> {key_str(s)}",
                    "different incidents",
                )
            )

    if _has_cycle(unique_nodes, edges):
        errors.append(ValidationError(ErrorCode.E_CYCLE, "graph", "not a DAG"))

    errors += _workflow_errors(unique_nodes, edges)
    errors += _reachability_errors(unique_nodes, scene)
    return errors
