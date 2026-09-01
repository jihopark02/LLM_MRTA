"""Core enums for the MRTA domain.

RESEARCH_CONTRACT.md §4 (task vocabulary), §5 (agents), §6 (agent model), §7 (task model).

Python 3.10 has no ``enum.StrEnum`` (added in 3.11), so we use the ``str`` mixin
pattern; ``Capability.AERIAL_RECON == "AERIAL_RECON"`` holds and YAML round-trips
as a plain string.
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
    MARKER_DISPENSER = "MARKER_DISPENSER"


class TaskType(str, Enum):
    AREA_RECON = "AREA_RECON"
    THERMAL_RECON = "THERMAL_RECON"
    SUPPRESSANT_DROP = "SUPPRESSANT_DROP"
    GROUND_INSPECTION = "GROUND_INSPECTION"
    HAZARD_MARKER_DEPLOY = "HAZARD_MARKER_DEPLOY"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    ASSIGNED = "ASSIGNED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
