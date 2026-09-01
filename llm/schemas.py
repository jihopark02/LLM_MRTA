"""Structured-output schemas for the LLM pipeline (RESEARCH_CONTRACT.md §12).

Step 1 emits a task list (task_type / target / priority only — §7); Step 2 emits
dependency edges as "TASK_TYPE:target" endpoint strings. Repair re-emits both.
These are the exact shapes the backend is asked to return; the resulting dict is
handed straight to ``validator.candidate.MissionCandidate.from_raw``.
"""

from pydantic import BaseModel, Field


class LLMTask(BaseModel):
    task_type: str
    target: str
    priority: int = Field(ge=1, le=10)


class LLMEdge(BaseModel):
    predecessor: str  # "TASK_TYPE:target"
    successor: str


class Step1Output(BaseModel):
    tasks: list[LLMTask]


class Step2Output(BaseModel):
    edges: list[LLMEdge]


class RepairOutput(BaseModel):
    tasks: list[LLMTask]
    edges: list[LLMEdge]


def to_candidate_dict(tasks: list[LLMTask], edges: list[LLMEdge]) -> dict:
    """The raw dict shape MissionCandidate.from_raw expects."""
    return {
        "tasks": [
            {"task_type": t.task_type, "target": t.target, "priority": t.priority}
            for t in tasks
        ],
        "edges": [[e.predecessor, e.successor] for e in edges],
    }
