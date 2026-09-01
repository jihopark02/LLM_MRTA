"""MissionPatch application + reconciliation (RESEARCH_CONTRACT.md §10, v1.4).

apply_patch runs the full §10 procedure on a clone and either commits the clone
or leaves the original untouched (step 8 transaction). Every patch is validated
against the FULL final candidate graph from scratch (§9 multi-transaction note),
never against "what this patch changed".

Note (D-006): with the fixed 5-type vocabulary and the strict workflow invariant
(§9 #10), no *valid* P2 patch changes an existing task's predecessor set — so
the reconciliation release path (steps 5-6) and E_RUNNING_LOCKED are implemented
and unit-tested here, but only become reachable end-to-end once RQ3 (P8) adds
recheck task types. #13 (terminal immutability) is reachable in P2.
"""

from dataclasses import dataclass

from core.enums import TaskStatus
from core.mission_state import MissionState
from core.task_graph import TaskGraph
from scenarios.compiler import compile_task, task_id_for
from scenarios.scene import Scene
from validator.errors import ErrorCode, ValidationError
from validator.hashing import VALIDATOR_VERSION, graph_hash, scene_hash
from validator.patch import (
    AddEdge,
    AddTask,
    MissionPatch,
    RemoveEdge,
    graph_edge_keys,
    graph_hash_nodes,
    pair_str,
    post_patch_keys,
    validate_patch_ops,
)
from validator.whole_graph import validate_structure

_TERMINAL = frozenset({TaskStatus.COMPLETED, TaskStatus.CANCELLED})
_RELEASE_FROM = frozenset({TaskStatus.ASSIGNED, TaskStatus.READY})


@dataclass(frozen=True, slots=True)
class PatchResult:
    accepted: bool
    rejection_errors: tuple[ValidationError, ...] = ()
    added_tasks: tuple[str, ...] = ()
    added_edges: tuple[tuple[str, str], ...] = ()
    removed_edges: tuple[tuple[str, str], ...] = ()
    directly_released_tasks: tuple[str, ...] = ()
    status_changes: tuple[tuple[str, str, str], ...] = ()
    graph_hash: str = ""
    scene_hash: str = ""
    validator_version: str = ""

    @property
    def error_codes(self) -> list[ErrorCode]:
        return sorted({e.code for e in self.rejection_errors})


def _reject(errors, scene) -> PatchResult:
    return PatchResult(
        accepted=False,
        rejection_errors=tuple(errors),
        scene_hash=scene_hash(scene),
        validator_version=VALIDATOR_VERSION,
    )


def _tid(key) -> str:
    return task_id_for(key[0], key[1])


def apply_patch(
    state: MissionState, patch: MissionPatch, scene: Scene
) -> tuple[MissionState, PatchResult]:
    base = state.graph

    # Step 2: raw op-list self-consistency.
    op_errors = validate_patch_ops(patch, base)
    if op_errors:
        return state, _reject(op_errors, scene)

    # Steps 3-4: symbolic canonical apply -> whole-graph invariants, before any
    # Task is materialised (a bad AddTask target is E_UNKNOWN_REF, not a crash).
    nodes, edges = post_patch_keys(patch, base)
    base_edge_keys = graph_edge_keys(base)
    final_edge_keys = set(edges)

    # #13 first: when a terminal task is involved its immutability is the more
    # informative failure than the #10 workflow break it also triggers.
    terminal_errors = _terminal_immutable_errors(base, base_edge_keys, final_edge_keys)
    if terminal_errors:
        return state, _reject(terminal_errors, scene)

    struct_errors = validate_structure(nodes, edges, scene)
    if struct_errors:
        return state, _reject(struct_errors, scene)

    # Materialise on a clone.
    work = state.clone()
    g = work.graph
    added_task_ids = [
        _materialise_add_task(g, scene, op)
        for op in patch.operations
        if isinstance(op, AddTask)
    ]
    removed_edge_ids = [
        _remove(g, op) for op in patch.operations if isinstance(op, RemoveEdge)
    ]
    added_edge_ids = [
        _add(g, op) for op in patch.operations if isinstance(op, AddEdge)
    ]

    # Steps 5-7: predecessor-set diff -> reconciliation -> assignment re-check.
    changed = _predecessor_diff(base, g)
    released, status_changes, recon_errors = _reconcile(work, base, changed)
    if recon_errors:
        return state, _reject(recon_errors, scene)

    assign_errors = _assignment_invariant_errors(work)
    if assign_errors:
        return state, _reject(assign_errors, scene)

    # Step 8: commit the clone.
    result = PatchResult(
        accepted=True,
        added_tasks=tuple(added_task_ids),
        added_edges=tuple(added_edge_ids),
        removed_edges=tuple(removed_edge_ids),
        directly_released_tasks=tuple(sorted(released)),
        status_changes=tuple(status_changes),
        graph_hash=graph_hash(graph_hash_nodes(g), sorted(final_edge_keys)),
        scene_hash=scene_hash(scene),
        validator_version=VALIDATOR_VERSION,
    )
    return work, result


# -- step helpers ----------------------------------------------------------


def _materialise_add_task(g: TaskGraph, scene: Scene, op: AddTask) -> str:
    task = compile_task(scene, op.task_type, op.target, op.priority)
    g.add_task(task)
    return task.task_id


def _remove(g: TaskGraph, op: RemoveEdge) -> tuple[str, str]:
    g.remove_edge(_tid(op.predecessor), _tid(op.successor))
    return (_tid(op.predecessor), _tid(op.successor))


def _add(g: TaskGraph, op: AddEdge) -> tuple[str, str]:
    g.add_edge(_tid(op.predecessor), _tid(op.successor))
    return (_tid(op.predecessor), _tid(op.successor))


def _predecessor_diff(base: TaskGraph, final: TaskGraph) -> set[str]:
    base_preds = {t.task_id: base.predecessors(t.task_id) for t in base.tasks}
    final_preds = {t.task_id: final.predecessors(t.task_id) for t in final.tasks}
    return {
        task_id
        for task_id in set(base_preds) | set(final_preds)
        if base_preds.get(task_id) != final_preds.get(task_id)
    }


def _reconcile(
    work: MissionState, base: TaskGraph, changed: set[str]
) -> tuple[list[str], list[tuple[str, str, str]], list[ValidationError]]:
    """§10 step 6. Returns (directly_released, status_changes, fatal_errors)."""
    g = work.graph
    released: list[str] = []
    status_changes: list[tuple[str, str, str]] = []

    for task_id in sorted(changed):
        if task_id not in base:  # new task, handled by recompute below
            continue
        base_status = base[task_id].status
        if base_status is TaskStatus.RUNNING:
            return [], [], [
                ValidationError(
                    ErrorCode.E_RUNNING_LOCKED,
                    task_id,
                    "predecessor change on a RUNNING task is not supported",
                )
            ]
        if base_status in _TERMINAL:
            return [], [], [
                ValidationError(ErrorCode.E_TERMINAL_IMMUTABLE, task_id, "incoming edge changed")
            ]
        if base_status in _RELEASE_FROM:
            task = g[task_id]
            before = task.status.value
            if base_status is TaskStatus.ASSIGNED:
                work.clear_assignment(task_id)
                released.append(task_id)
            task.status = TaskStatus.PENDING
            status_changes.append((task_id, before, TaskStatus.PENDING.value))

    ready_before = g.ids_with_status(TaskStatus.READY)
    g.recompute_ready()
    ready_after = g.ids_with_status(TaskStatus.READY)
    for task_id in sorted(ready_after - ready_before):
        status_changes.append((task_id, TaskStatus.PENDING.value, TaskStatus.READY.value))
    for task_id in sorted(ready_before - ready_after):
        if all(sc[0] != task_id for sc in status_changes):
            status_changes.append((task_id, TaskStatus.READY.value, TaskStatus.PENDING.value))

    return released, status_changes, []


def _terminal_immutable_errors(
    base: TaskGraph, base_edges: set, final_edges: set
) -> list[ValidationError]:
    terminal_ids = {t.task_id for t in base.tasks if t.status in _TERMINAL}
    if not terminal_ids:
        return []
    base_by_key = {(t.task_type, t.target): t.task_id for t in base.tasks}

    errors: list[ValidationError] = []
    for pred_key, succ_key in sorted(base_edges ^ final_edges):
        pred_id = base_by_key.get(pred_key)
        succ_id = base_by_key.get(succ_key)
        if succ_id in terminal_ids:
            errors.append(
                ValidationError(
                    ErrorCode.E_TERMINAL_IMMUTABLE,
                    succ_id,
                    f"incoming edge {pair_str((pred_key, succ_key))} changed on a terminal task",
                )
            )
        if pred_id in terminal_ids and succ_id is not None:
            if base[succ_id].status is TaskStatus.RUNNING:
                errors.append(
                    ValidationError(
                        ErrorCode.E_TERMINAL_IMMUTABLE,
                        pred_id,
                        f"outgoing rewire toward RUNNING successor {succ_id}",
                    )
                )
    return errors


_ACTIVE = frozenset({TaskStatus.ASSIGNED, TaskStatus.RUNNING})


def _assignment_invariant_errors(state: MissionState) -> list[ValidationError]:
    """§10 step 7 assignment consistency invariant (D-007, rules 1-4)."""
    errors: list[ValidationError] = []

    def err(subject: str, detail: str) -> None:
        errors.append(ValidationError(ErrorCode.E_SCHEMA, subject, detail))

    # task_id -> agents that hold it in bundle or path
    holders: dict[str, list[str]] = {}
    for agent in state.agents.values():
        for task_id in set(agent.bundle) | set(agent.path):
            holders.setdefault(task_id, []).append(agent.agent_id)

    for task in state.graph.tasks:
        active = task.status in _ACTIVE
        owner = task.assigned_agent
        held_by = sorted(holders.get(task.task_id, []))

        if owner is not None and owner not in state.agents:
            err(task.task_id, f"assigned_agent {owner!r} is not in the fleet")
        if active and owner is None:
            err(task.task_id, "ASSIGNED/RUNNING task has no assigned_agent")
        if not active and owner is not None:
            err(task.task_id, f"non-active task still assigned to {owner!r}")

        if active:
            if held_by != [owner] and owner is not None:
                err(task.task_id, f"held by {held_by}, expected exactly [{owner!r}]")
        else:
            if held_by:
                err(task.task_id, f"non-active task still in bundle/path of {held_by}")
            if task.task_id in state.winning_bids:
                err(task.task_id, "non-active task has a stale winning_bid")

    for task_id, agents in holders.items():
        if len(agents) > 1:
            err(task_id, f"in bundle/path of multiple agents: {sorted(agents)}")

    return errors
