"""MissionPatch operations + raw op-list validation (RESEARCH_CONTRACT.md §10, D-005).

§10 step 2: the raw operation list is checked for self-consistency BEFORE it
enters the graph — set/graph representation would lose the duplicate information.
All such failures are E_PATCH_CONFLICT (E_SCHEMA for a malformed op). Once the
list is self-consistent, applying the ops in canonical order
``AddTask -> RemoveEdge -> AddEdge`` yields a graph independent of the caller's
op ordering.

Graph mutation + reconciliation (steps 3-8) is validator/patch_apply.py.
"""

from collections import Counter
from dataclasses import dataclass, field

from core.enums import TaskType
from core.task_graph import TaskGraph
from validator.candidate import TaskKey, key_str
from validator.errors import ErrorCode, ValidationError

_EdgeKey = tuple[TaskKey, TaskKey]


@dataclass(frozen=True, slots=True)
class AddTask:
    task_type: TaskType
    target: str
    priority: int

    @property
    def key(self) -> TaskKey:
        return (self.task_type, self.target)


@dataclass(frozen=True, slots=True)
class AddEdge:
    predecessor: TaskKey
    successor: TaskKey

    @property
    def edge(self) -> _EdgeKey:
        return (self.predecessor, self.successor)


@dataclass(frozen=True, slots=True)
class RemoveEdge:
    predecessor: TaskKey
    successor: TaskKey

    @property
    def edge(self) -> _EdgeKey:
        return (self.predecessor, self.successor)


MissionOp = AddTask | AddEdge | RemoveEdge


@dataclass(slots=True)
class MissionPatch:
    operations: list[MissionOp] = field(default_factory=list)


def pair_str(edge: _EdgeKey) -> str:
    return f"{key_str(edge[0])} -> {key_str(edge[1])}"


def graph_task_key(graph: TaskGraph, task_id: str) -> TaskKey:
    task = graph[task_id]
    return (task.task_type, task.target)


def graph_edge_keys(graph: TaskGraph) -> set[_EdgeKey]:
    return {
        (graph_task_key(graph, p), graph_task_key(graph, s)) for p, s in graph.edges
    }


def graph_task_keys(graph: TaskGraph) -> set[TaskKey]:
    return {graph_task_key(graph, tid) for tid in (t.task_id for t in graph.tasks)}


def graph_hash_nodes(graph: TaskGraph) -> list[tuple[TaskType, str, int]]:
    return [(t.task_type, t.target, t.priority) for t in graph.tasks]


def _valid_endpoint(ep: object) -> bool:
    return (
        isinstance(ep, tuple)
        and len(ep) == 2
        and isinstance(ep[0], TaskType)
        and isinstance(ep[1], str)
    )


def _op_schema_error(op: object, i: int) -> ValidationError | None:
    """Runtime field check — do not trust the type hints (D-007)."""
    where = f"operations[{i}]"
    if isinstance(op, AddTask):
        if not isinstance(op.task_type, TaskType):
            return ValidationError(ErrorCode.E_SCHEMA, where, f"task_type {op.task_type!r}")
        if not isinstance(op.target, str):
            return ValidationError(ErrorCode.E_SCHEMA, where, "target must be str")
        if not isinstance(op.priority, int) or isinstance(op.priority, bool):
            return ValidationError(ErrorCode.E_SCHEMA, where, "priority must be int")
        if not 1 <= op.priority <= 10:  # contract §7 / D-008
            return ValidationError(
                ErrorCode.E_SCHEMA, where, f"priority {op.priority} not in 1..10"
            )
        return None
    if isinstance(op, (AddEdge, RemoveEdge)):
        if not _valid_endpoint(op.predecessor) or not _valid_endpoint(op.successor):
            return ValidationError(ErrorCode.E_SCHEMA, where, "endpoint must be (TaskType, str)")
        return None
    return ValidationError(ErrorCode.E_SCHEMA, where, f"unknown op {type(op).__name__}")


def validate_patch_ops(patch: MissionPatch, base: TaskGraph) -> list[ValidationError]:
    errors: list[ValidationError] = []

    def conflict(subject: str, detail: str) -> None:
        errors.append(ValidationError(ErrorCode.E_PATCH_CONFLICT, subject, detail))

    if not isinstance(patch.operations, list):
        return [ValidationError(ErrorCode.E_SCHEMA, "operations", "must be a list")]

    ops: list[MissionOp] = []
    for i, op in enumerate(patch.operations):
        schema_error = _op_schema_error(op, i)
        if schema_error is not None:
            errors.append(schema_error)
        else:
            ops.append(op)  # only field-valid ops reach the conflict checks

    base_task_keys = graph_task_keys(base)
    base_edges = graph_edge_keys(base)

    for key, n in Counter(o.key for o in ops if isinstance(o, AddTask)).items():
        if n > 1:
            conflict(key_str(key), "AddTask appears more than once")
        if key in base_task_keys:
            conflict(key_str(key), "AddTask duplicates an existing task")

    add_edges = [o.edge for o in ops if isinstance(o, AddEdge)]
    rem_edges = [o.edge for o in ops if isinstance(o, RemoveEdge)]
    for edge, n in Counter(add_edges).items():
        if n > 1:
            conflict(pair_str(edge), "AddEdge appears more than once")
        if edge in base_edges:
            conflict(pair_str(edge), "AddEdge already exists in the graph")
    for edge, n in Counter(rem_edges).items():
        if n > 1:
            conflict(pair_str(edge), "RemoveEdge appears more than once")

    add_set, rem_set = set(add_edges), set(rem_edges)
    for edge in sorted(add_set & rem_set):
        conflict(pair_str(edge), "edge is both added and removed")
    for edge in sorted(rem_set):
        if edge not in base_edges and edge not in add_set:
            conflict(pair_str(edge), "RemoveEdge targets an edge that does not exist")

    return errors


def post_patch_keys(
    patch: MissionPatch, base: TaskGraph
) -> tuple[list[TaskKey], list[_EdgeKey]]:
    """Symbolic result of applying the (already validated) ops in canonical order.

    Used to run the whole-graph invariants before any Task is materialised.
    """
    nodes = list(graph_task_keys(base))
    nodes += [o.key for o in patch.operations if isinstance(o, AddTask)]

    edges = set(graph_edge_keys(base))
    for op in patch.operations:  # RemoveEdge before AddEdge (canonical)
        if isinstance(op, RemoveEdge):
            edges.discard(op.edge)
    for op in patch.operations:
        if isinstance(op, AddEdge):
            edges.add(op.edge)
    return nodes, sorted(edges)
