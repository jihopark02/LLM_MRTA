"""The §4 incident workflow as an ordered chain (RESEARCH_CONTRACT.md §18).

The Validator states the same rule as a predecessor map
(``validator.whole_graph.WORKFLOW_PREDECESSOR``); the planning session needs it
as an *order* — to summarise how far an incident's response has been planned
and to expand "take it up to <step>" into a contiguous prefix. The assertions
below keep this tuple honest against the Validator's map, which stays the
single source of truth for the rule itself.
"""

from core.enums import TaskType
from validator.whole_graph import WORKFLOW_PREDECESSOR

WORKFLOW_CHAIN: tuple[TaskType, ...] = (
    TaskType.THERMAL_RECON,
    TaskType.SUPPRESSANT_DROP,
    TaskType.GROUND_INSPECTION,
    TaskType.GROUND_SUPPRESSION,
)

assert WORKFLOW_CHAIN[0] not in WORKFLOW_PREDECESSOR, "chain head must have no predecessor"
assert set(WORKFLOW_CHAIN[1:]) == set(WORKFLOW_PREDECESSOR), "chain tail != predecessor map keys"
assert all(
    WORKFLOW_PREDECESSOR[succ] is pred
    for pred, succ in zip(WORKFLOW_CHAIN, WORKFLOW_CHAIN[1:], strict=False)
), "chain order disagrees with WORKFLOW_PREDECESSOR"


__all__ = ["WORKFLOW_CHAIN"]
