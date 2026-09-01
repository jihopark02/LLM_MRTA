"""Validator error codes (RESEARCH_CONTRACT.md §9 invariant table, §10).

Each code maps to a numbered §9 invariant, except:
- E_PATCH_CONFLICT: §10 step 2, raw operation-list self-consistency (D-005).
- E_RUNNING_LOCKED: §10 step 6, a patch that would change a RUNNING task's
  predecessor set is rejected whole.
"""

from dataclasses import dataclass
from enum import Enum


class ErrorCode(str, Enum):
    E_SCHEMA = "E_SCHEMA"                      # §9 #1
    E_DUPLICATE_ID = "E_DUPLICATE_ID"          # §9 #2
    E_TYPE_NOT_ALLOWED = "E_TYPE_NOT_ALLOWED"  # §9 #3
    E_UNKNOWN_REF = "E_UNKNOWN_REF"            # §9 #4 (task target), #5 (edge endpoint)
    E_SELF_LOOP = "E_SELF_LOOP"               # §9 #6
    E_DUPLICATE_EDGE = "E_DUPLICATE_EDGE"      # §9 #7
    E_CYCLE = "E_CYCLE"                        # §9 #8
    E_INFEASIBLE = "E_INFEASIBLE"             # §9 #9
    E_WORKFLOW = "E_WORKFLOW"                 # §9 #10
    E_CROSS_INCIDENT = "E_CROSS_INCIDENT"      # §9 #11
    E_UNREACHABLE = "E_UNREACHABLE"           # §9 #12
    E_TERMINAL_IMMUTABLE = "E_TERMINAL_IMMUTABLE"  # §9 #13
    E_PATCH_CONFLICT = "E_PATCH_CONFLICT"      # §10 step 2 (D-005)
    E_RUNNING_LOCKED = "E_RUNNING_LOCKED"      # §10 step 6


@dataclass(frozen=True, slots=True, order=True)
class ValidationError:
    code: ErrorCode
    subject: str  # task_id, "TYPE:target -> TYPE:target", "patch", ...
    detail: str = ""

    def __str__(self) -> str:
        tail = f" — {self.detail}" if self.detail else ""
        return f"{self.code.value}[{self.subject}]{tail}"
