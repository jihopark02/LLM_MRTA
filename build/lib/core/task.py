"""Task data model (RESEARCH_CONTRACT.md §7).

The LLM produces only ``task_type`` + ``target`` + ``priority``. Everything else
(``task_id``, ``position``, ``required_capabilities``, ``eligible_platforms``,
``duration``) is resolved deterministically by ``scenarios/compiler.py`` from
the semantic scene and the default capability table.

``status`` is NOT stored independently in YAML; it is recomputed from the
predecessor state in the task graph (see ``core/task_graph.py``).
"""

import math
from dataclasses import dataclass

from core.enums import Capability, PlatformKind, TaskStatus, TaskType


@dataclass(slots=True)
class Task:
    task_id: str
    task_type: TaskType
    target: str  # area_id or incident_id
    position: tuple[float, float]
    priority: int
    required_capabilities: frozenset[Capability]
    eligible_platforms: frozenset[PlatformKind]
    duration: float
    status: TaskStatus
    assigned_agent: str | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.duration) or self.duration <= 0.0:
            raise ValueError(
                f"{self.task_id}: duration must be finite and positive, got {self.duration!r}"
            )
