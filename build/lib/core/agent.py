"""Generic agent model (RESEARCH_CONTRACT.md §6).

Platform-specific configuration (PX4 velocity params, Gazebo model, UGV route
node, differential-drive params) does NOT live here — it goes in a separate
platform adapter (``execution/px4_adapter.py``, ``execution/ugv_adapter.py``),
implemented in P7.
"""

from dataclasses import dataclass, field

from core.enums import Capability, PlatformKind


@dataclass(slots=True)
class Agent:
    agent_id: str
    platform_kind: PlatformKind
    capabilities: frozenset[Capability]
    initial_position: tuple[float, float]
    position: tuple[float, float]
    speed: float
    bundle: list[str] = field(default_factory=list)
    path: list[str] = field(default_factory=list)
    current_task: str | None = None

    def has_capabilities(self, required: frozenset[Capability]) -> bool:
        return required <= self.capabilities
