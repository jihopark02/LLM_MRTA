"""Structured mission-level policy extracted from an operator command (§22).

The task graph contains work that can be instantiated now.  A response to a
future, not-yet-known incident cannot name a target task yet, so the narrow
``FIRE_DETECTED`` contingency lives beside the graph as a frozen directive.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.enums import TaskType
from interaction.workflow import WORKFLOW_CHAIN


@dataclass(frozen=True, slots=True)
class MissionDirective:
    """The only conditional policy P12 supports.

    ``None`` means that reporting/detecting a fire does not imply a response
    workflow.  A concrete step means instantiate the canonical workflow prefix
    through that step when an incident becomes known.
    """

    incident_response_up_to: TaskType | None = None

    def __post_init__(self) -> None:
        step = self.incident_response_up_to
        if step is not None and step not in WORKFLOW_CHAIN:
            raise ValueError(f"not an incident workflow step: {step!r}")

    @classmethod
    def from_slot(cls, value: str | None) -> MissionDirective:
        return cls(None if value is None else TaskType(value))

    def to_dict(self) -> dict[str, str | None]:
        step = self.incident_response_up_to
        return {"incident_response_up_to": step.value if step is not None else None}


__all__ = ["MissionDirective"]
