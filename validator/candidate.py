"""Raw mission candidate representation (RESEARCH_CONTRACT.md §12, D-003, D-005).

The LLM pipeline (P5) emits a task list (task_type / target) plus an edge list;
priority is scene-derived by the compiler, not part of the candidate (D-022).
The whole-graph Validator inspects THIS raw representation — a plain
list, duplicates preserved — before anything is compiled into a TaskGraph,
because a set/graph loses the duplicate information that E_DUPLICATE_ID /
E_DUPLICATE_EDGE need.

``from_raw`` handles invariant #1 (E_SCHEMA) and #3 (E_TYPE_NOT_ALLOWED).
``consistency_errors`` handles the other raw-list checks: #2 (E_DUPLICATE_ID),
#6 (E_SELF_LOOP), #7 (E_DUPLICATE_EDGE), and the edge half of #5 (E_UNKNOWN_REF,
endpoint is not one of the candidate tasks).
"""

from dataclasses import dataclass, field

from core.enums import TaskType
from validator.errors import ErrorCode, ValidationError

TaskKey = tuple[TaskType, str]


def key_str(key: TaskKey) -> str:
    return f"{key[0].value}:{key[1]}"


@dataclass(frozen=True, slots=True)
class CandidateTask:
    task_type: TaskType
    target: str

    @property
    def key(self) -> TaskKey:
        return (self.task_type, self.target)


@dataclass(frozen=True, slots=True)
class CandidateEdge:
    predecessor: TaskKey
    successor: TaskKey

    def __str__(self) -> str:
        return f"{key_str(self.predecessor)} -> {key_str(self.successor)}"


@dataclass(slots=True)
class MissionCandidate:
    tasks: list[CandidateTask] = field(default_factory=list)
    edges: list[CandidateEdge] = field(default_factory=list)

    # -- parsing (invariant #1, #3) ------------------------------------
    @classmethod
    def from_raw(
        cls, raw: object
    ) -> tuple["MissionCandidate | None", list[ValidationError]]:
        errors: list[ValidationError] = []
        ok_shape = (
            isinstance(raw, dict)
            and isinstance(raw.get("tasks"), list)
            and isinstance(raw.get("edges"), list)
        )
        if not ok_shape:
            errors.append(
                ValidationError(
                    ErrorCode.E_SCHEMA, "candidate", "expected {tasks: [...], edges: [...]}"
                )
            )
            return None, errors
        extra = set(raw) - {"tasks", "edges"}
        if extra:
            errors.append(
                ValidationError(ErrorCode.E_SCHEMA, "candidate", f"unexpected keys {sorted(extra)}")
            )
            return None, errors

        tasks = [
            t
            for i, entry in enumerate(raw["tasks"])
            if (t := _parse_task(entry, i, errors)) is not None
        ]
        edges = [
            e
            for i, entry in enumerate(raw["edges"])
            if (e := _parse_edge(entry, i, errors)) is not None
        ]
        return cls(tasks, edges), errors

    # -- raw-list consistency (invariant #2, #5-edge, #6, #7) ----------
    def consistency_errors(self) -> list[ValidationError]:
        errors: list[ValidationError] = []

        seen_keys: set[TaskKey] = set()
        for t in self.tasks:
            if t.key in seen_keys:
                errors.append(
                    ValidationError(
                        ErrorCode.E_DUPLICATE_ID, key_str(t.key), "task appears more than once"
                    )
                )
            seen_keys.add(t.key)

        seen_edges: set[tuple[TaskKey, TaskKey]] = set()
        for e in self.edges:
            pair = (e.predecessor, e.successor)
            if e.predecessor == e.successor:
                errors.append(ValidationError(ErrorCode.E_SELF_LOOP, key_str(e.predecessor)))
            if pair in seen_edges:
                errors.append(ValidationError(ErrorCode.E_DUPLICATE_EDGE, str(e)))
            seen_edges.add(pair)
            for endpoint in (e.predecessor, e.successor):
                if endpoint not in seen_keys:
                    errors.append(
                        ValidationError(
                            ErrorCode.E_UNKNOWN_REF,
                            str(e),
                            f"endpoint {key_str(endpoint)} is not a candidate task",
                        )
                    )
        return errors


def _parse_task(
    entry: object, i: int, errors: list[ValidationError]
) -> CandidateTask | None:
    if not isinstance(entry, dict):
        errors.append(ValidationError(ErrorCode.E_SCHEMA, f"tasks[{i}]", "not an object"))
        return None
    extra = set(entry) - {"task_type", "target"}
    if extra:
        errors.append(
            ValidationError(ErrorCode.E_SCHEMA, f"tasks[{i}]", f"unexpected keys {sorted(extra)}")
        )
        return None
    tt_raw = entry.get("task_type")
    target = entry.get("target")
    if not (isinstance(tt_raw, str) and isinstance(target, str)):
        errors.append(
            ValidationError(
                ErrorCode.E_SCHEMA, f"tasks[{i}]", "need task_type:str, target:str"
            )
        )
        return None
    try:
        task_type = TaskType(tt_raw)
    except ValueError:
        errors.append(
            ValidationError(ErrorCode.E_TYPE_NOT_ALLOWED, f"tasks[{i}]", repr(tt_raw))
        )
        return None
    return CandidateTask(task_type, target)


def _parse_edge(
    entry: object, i: int, errors: list[ValidationError]
) -> CandidateEdge | None:
    if not isinstance(entry, (list, tuple)) or len(entry) != 2:
        errors.append(
            ValidationError(ErrorCode.E_SCHEMA, f"edges[{i}]", "expected [predecessor, successor]")
        )
        return None
    endpoints: list[TaskKey] = []
    for half in entry:
        if not isinstance(half, str) or half.count(":") != 1:
            errors.append(
                ValidationError(
                    ErrorCode.E_SCHEMA, f"edges[{i}]", "endpoint must be 'TASK_TYPE:target'"
                )
            )
            return None
        tt_raw, target = half.split(":", 1)
        try:
            endpoints.append((TaskType(tt_raw), target))
        except ValueError:
            errors.append(
                ValidationError(ErrorCode.E_TYPE_NOT_ALLOWED, f"edges[{i}]", repr(tt_raw))
            )
            return None
    return CandidateEdge(endpoints[0], endpoints[1])
