"""Deterministic Mission Compiler — ResolvedMissionIR → canonical graph / patch
(D-076, §18.3).

Purely mechanical: the resolver already turned every operator into concrete
zone / incident id sets and rejected the ambiguous cases, so this module only
expands recon zones into ``AREA_RECON`` tasks and each response clause into the
contiguous ``GROUND_INSPECTION [→ GROUND_SUPPRESSION]`` workflow prefix, dedupes
identical (task_type, target) / edges across clauses (S4), and emits either a
fresh graph (`NEW_MISSION`) or an additive patch (`UPDATE_MISSION` — AddTask /
AddEdge only, never a removal).
"""

from __future__ import annotations

from core.enums import TaskType
from core.task_graph import TaskGraph
from interaction.resolve import ResolvedMissionIR
from interaction.workflow import WORKFLOW_CHAIN
from scenarios.compiler import compile_reference_graph
from scenarios.scene import Scene
from validator.patch import AddEdge, AddTask, MissionPatch

_TaskSpec = tuple[TaskType, str]
_EdgeSpec = tuple[_TaskSpec, _TaskSpec]


def _chain_prefix(up_to: str) -> tuple[TaskType, ...]:
    step = TaskType(up_to)
    return WORKFLOW_CHAIN[: WORKFLOW_CHAIN.index(step) + 1]


def _specs(ir: ResolvedMissionIR) -> tuple[list[_TaskSpec], list[_EdgeSpec]]:
    tasks: list[_TaskSpec] = []
    edges: list[_EdgeSpec] = []
    seen_t: set[_TaskSpec] = set()
    seen_e: set[_EdgeSpec] = set()

    def add_task(spec: _TaskSpec) -> None:
        if spec not in seen_t:
            seen_t.add(spec)
            tasks.append(spec)

    for clause in ir.recon:
        for zid in clause.zone_ids:
            add_task((TaskType.AREA_RECON, zid))

    for clause in ir.responses:
        steps = _chain_prefix(clause.response_up_to)
        for iid in clause.incident_ids:
            chain = [(step, iid) for step in steps]
            for spec in chain:
                add_task(spec)
            for a, b in zip(chain, chain[1:], strict=False):
                if (a, b) not in seen_e:
                    seen_e.add((a, b))
                    edges.append((a, b))

    return tasks, edges


def compile_new_graph(ir: ResolvedMissionIR, scene: Scene) -> TaskGraph:
    tasks, edges = _specs(ir)
    return compile_reference_graph(scene, tasks, edges)


def compile_patch(ir: ResolvedMissionIR, current: TaskGraph) -> MissionPatch:
    """Additive patch. An empty ``operations`` list means NO_CHANGE — every
    requested task/edge is already in ``current`` (§18.6)."""
    tasks, edges = _specs(ir)
    have_tasks = {(t.task_type, t.target) for t in current.tasks}
    have_edges = {
        ((current[p].task_type, current[p].target),
         (current[s].task_type, current[s].target))
        for p, s in current.edges
    }
    ops: list = [AddTask(tt, tgt) for tt, tgt in tasks if (tt, tgt) not in have_tasks]
    ops += [AddEdge(a, b) for a, b in edges if (a, b) not in have_edges]
    return MissionPatch(ops)


__all__ = ["compile_new_graph", "compile_patch"]
