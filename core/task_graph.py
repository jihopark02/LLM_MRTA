"""Task dependency graph (RESEARCH_CONTRACT.md §7, §9, §11).

A directed graph of ``Task`` nodes with predecessor -> successor edges. Task
status is derived from predecessor status, not stored independently: a task is
READY once every predecessor is COMPLETED, PENDING otherwise. ASSIGNED / RUNNING
/ COMPLETED / CANCELLED are set by the allocator and executor and left untouched
here.

The full whole-graph Validator with error codes and transactional patches is
P2. This module only provides the structural primitives P1 needs (cycle
detection, edge-reference validity) plus the READY-frontier recompute.
"""

from collections import deque

from core.enums import TaskStatus
from core.task import Task

_RECOMPUTABLE = frozenset({TaskStatus.PENDING, TaskStatus.READY})


class CycleError(ValueError):
    """Raised when the graph contains a directed cycle (contract §9 #8)."""


class TaskGraph:
    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}
        self._successors: dict[str, set[str]] = {}
        self._predecessors: dict[str, set[str]] = {}

    # -- construction -----------------------------------------------------
    def add_task(self, task: Task) -> None:
        if task.task_id in self._tasks:
            raise ValueError(f"duplicate task_id: {task.task_id}")
        self._tasks[task.task_id] = task
        self._successors.setdefault(task.task_id, set())
        self._predecessors.setdefault(task.task_id, set())

    def add_edge(self, predecessor: str, successor: str) -> None:
        self._successors.setdefault(predecessor, set()).add(successor)
        self._predecessors.setdefault(successor, set()).add(predecessor)

    # -- access ---------------------------------------------------------
    def __contains__(self, task_id: str) -> bool:
        return task_id in self._tasks

    def __getitem__(self, task_id: str) -> Task:
        return self._tasks[task_id]

    def __len__(self) -> int:
        return len(self._tasks)

    @property
    def tasks(self) -> list[Task]:
        return list(self._tasks.values())

    @property
    def edges(self) -> set[tuple[str, str]]:
        return {(p, s) for p, succs in self._successors.items() for s in succs}

    def predecessors(self, task_id: str) -> set[str]:
        return set(self._predecessors.get(task_id, ()))

    def successors(self, task_id: str) -> set[str]:
        return set(self._successors.get(task_id, ()))

    # -- structural checks (P1 gate item 4) ----------------------------
    def reference_errors(self) -> list[str]:
        """Edges whose endpoints are unknown tasks, or self-loops (§9 #5, #6)."""
        errors: list[str] = []
        for pred, succ in sorted(self.edges):
            if pred == succ:
                errors.append(f"self-loop: {pred}")
            if pred not in self._tasks:
                errors.append(f"edge references unknown task: {pred}")
            if succ not in self._tasks:
                errors.append(f"edge references unknown task: {succ}")
        return errors

    def topological_order(self) -> list[str]:
        """Kahn's algorithm; raises CycleError if the graph is not a DAG (§9 #8)."""
        indegree = {tid: len(self._predecessors.get(tid, ())) for tid in self._tasks}
        queue = deque(sorted(tid for tid, d in indegree.items() if d == 0))
        order: list[str] = []
        while queue:
            tid = queue.popleft()
            order.append(tid)
            for succ in sorted(self._successors.get(tid, ())):
                indegree[succ] -= 1
                if indegree[succ] == 0:
                    queue.append(succ)
        if len(order) != len(self._tasks):
            raise CycleError(sorted(set(self._tasks) - set(order)))
        return order

    def has_cycle(self) -> bool:
        try:
            self.topological_order()
        except CycleError:
            return True
        return False

    # -- READY-frontier recompute (§7, §11) ---------------------------
    def recompute_ready(self) -> None:
        """PENDING/READY tasks become READY iff every predecessor is COMPLETED."""
        for tid, task in self._tasks.items():
            if task.status not in _RECOMPUTABLE:
                continue
            all_done = all(
                self._tasks[p].status is TaskStatus.COMPLETED
                for p in self._predecessors.get(tid, ())
            )
            task.status = TaskStatus.READY if all_done else TaskStatus.PENDING

    def ids_with_status(self, status: TaskStatus) -> set[str]:
        return {tid for tid, t in self._tasks.items() if t.status is status}
