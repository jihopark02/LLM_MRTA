"""Mission execution state (RESEARCH_CONTRACT.md §10).

A TaskGraph plus the fleet and the current allocation. MissionPatch processing
(validator/patch.py) clones this, applies operations to the clone, validates,
reconciles assignments from the start/end diff, and commits or rolls back.
"""

from dataclasses import dataclass, field, replace

from core.agent import Agent
from core.task_graph import TaskGraph


@dataclass(slots=True)
class MissionState:
    graph: TaskGraph
    agents: dict[str, Agent]
    winning_bids: dict[str, float] = field(default_factory=dict)

    def clone(self) -> "MissionState":
        return MissionState(
            graph=self.graph.clone(),
            agents={
                aid: replace(a, bundle=list(a.bundle), path=list(a.path))
                for aid, a in self.agents.items()
            },
            winning_bids=dict(self.winning_bids),
        )

    def clear_assignment(self, task_id: str) -> None:
        """Drop any allocation of ``task_id`` — from the task and from whichever
        agent holds it in its bundle/path (§10 step 6, ASSIGNED -> PENDING)."""
        task = self.graph[task_id]
        task.assigned_agent = None
        self.winning_bids.pop(task_id, None)
        for agent in self.agents.values():
            if task_id in agent.bundle:
                agent.bundle.remove(task_id)
            if task_id in agent.path:
                agent.path.remove(task_id)
            if agent.current_task == task_id:
                agent.current_task = None
