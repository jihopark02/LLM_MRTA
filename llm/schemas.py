"""Structured-output schemas for the LLM pipeline (RESEARCH_CONTRACT.md §12).

Step 1 emits a task list (task_type / target only — priority is scene-derived by
the compiler, §7 / D-022); Step 2 emits dependency edges as "TASK_TYPE:target"
endpoint strings. Repair re-emits both. These are the exact shapes the backend
is asked to return; the resulting dict is handed straight to
``validator.candidate.MissionCandidate.from_raw``.

``extra="forbid"`` + ``strict=True`` on every model: the contract's schema check
restricts allowed keys and types exactly (§7) — an extra field (a model-invented
``priority`` or ``position``) or a coerced type (``target=123``) must fail here,
not be silently dropped or coerced into something that looks valid.
"""

from pydantic import BaseModel, ConfigDict


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class LLMTask(_StrictModel):
    task_type: str
    target: str


class LLMEdge(_StrictModel):
    predecessor: str  # "TASK_TYPE:target"
    successor: str


class Step1Output(_StrictModel):
    tasks: list[LLMTask]


class Step2Output(_StrictModel):
    edges: list[LLMEdge]


class RepairOutput(_StrictModel):
    tasks: list[LLMTask]
    edges: list[LLMEdge]


def to_candidate_dict(tasks: list[LLMTask], edges: list[LLMEdge]) -> dict:
    """The raw dict shape MissionCandidate.from_raw expects."""
    return {
        "tasks": [{"task_type": t.task_type, "target": t.target} for t in tasks],
        "edges": [[e.predecessor, e.successor] for e in edges],
    }
