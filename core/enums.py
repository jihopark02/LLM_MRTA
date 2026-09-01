"""Core enums for the MRTA domain.

RESEARCH_CONTRACT.md §3 (incident state), §4 (task vocabulary), §5 (agents),
§6 (agent model), §7 (task model).

Python 3.10 has no ``enum.StrEnum`` (added in 3.11), so we use the ``str`` mixin
pattern: ``Capability.AERIAL_RECON == "AERIAL_RECON"`` holds, so YAML *reading*
needs no custom loader. These values do NOT auto-serialize — ``yaml.safe_dump``
raises on them — so at any serialization boundary write ``member.value``.
"""

from enum import Enum


class PlatformKind(str, Enum):
    UAV = "UAV"
    UGV = "UGV"


class Capability(str, Enum):
    AERIAL_RECON = "AERIAL_RECON"
    THERMAL_SENSOR = "THERMAL_SENSOR"
    SUPPRESSANT_PAYLOAD = "SUPPRESSANT_PAYLOAD"
    GROUND_MOBILITY = "GROUND_MOBILITY"
    SUPPRESSANT_APPLICATOR = "SUPPRESSANT_APPLICATOR"


class TaskType(str, Enum):
    AREA_RECON = "AREA_RECON"
    THERMAL_RECON = "THERMAL_RECON"
    SUPPRESSANT_DROP = "SUPPRESSANT_DROP"
    GROUND_INSPECTION = "GROUND_INSPECTION"
    GROUND_SUPPRESSION = "GROUND_SUPPRESSION"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    ASSIGNED = "ASSIGNED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class IncidentStatus(str, Enum):
    # Contract §3: incidents are given as already requiring a response; nothing
    # in the system decides whether a fire exists. RESPONSE_REQUIRED is the only
    # state the contract defines.
    RESPONSE_REQUIRED = "RESPONSE_REQUIRED"
