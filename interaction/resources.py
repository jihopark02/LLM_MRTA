"""Deterministic resource constraints for P13 natural-language missions.

The LLM may propose constraints, never assignments.  This module owns their
strict domain representation and validates scene-dependent agent references;
``allocation.team`` owns the exhaustive, deterministic team search.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.enums import PlatformKind
from scenarios.scene import Scene


class ResourceRequestError(ValueError):
    """A structurally valid request cannot be grounded against this scene."""

    code = "RESOURCE_SCHEMA"


@dataclass(frozen=True, slots=True)
class CountConstraint:
    """Allowed active-agent count for one platform."""

    exact: int | None = None
    minimum: int | None = None
    maximum: int | None = None

    def __post_init__(self) -> None:
        for label, value in (
            ("exact", self.exact),
            ("minimum", self.minimum),
            ("maximum", self.maximum),
        ):
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise ValueError(f"{label} must be a non-negative int, got {value!r}")
        if self.exact is not None and (self.minimum is not None or self.maximum is not None):
            raise ValueError("exact cannot be combined with minimum or maximum")
        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise ValueError("minimum cannot exceed maximum")

    @property
    def constrained(self) -> bool:
        return self.exact is not None or self.minimum is not None or self.maximum is not None

    def permitted_sizes(self, available: int) -> tuple[int, ...]:
        if not isinstance(available, int) or isinstance(available, bool) or available < 0:
            raise ValueError("available must be a non-negative int")
        if self.exact is not None:
            return (self.exact,) if self.exact <= available else ()
        low = self.minimum if self.minimum is not None else 0
        high = self.maximum if self.maximum is not None else available
        high = min(high, available)
        return tuple(range(low, high + 1)) if low <= high else ()

    def to_dict(self) -> dict[str, int | None]:
        return {"exact": self.exact, "minimum": self.minimum, "maximum": self.maximum}


@dataclass(frozen=True, slots=True)
class ResourceRequest:
    """Mission-level active-team constraints extracted from one command."""

    uav: CountConstraint = field(default_factory=CountConstraint)
    ugv: CountConstraint = field(default_factory=CountConstraint)
    required_agents: tuple[str, ...] = ()
    excluded_agents: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.uav, CountConstraint) or not isinstance(
            self.ugv, CountConstraint
        ):
            raise ValueError("uav and ugv must be CountConstraint values")
        for label, values in (
            ("required_agents", self.required_agents),
            ("excluded_agents", self.excluded_agents),
        ):
            if not isinstance(values, tuple) or not all(
                isinstance(value, str) and value for value in values
            ):
                raise ValueError(f"{label} must be a tuple of non-empty agent ids")
            if len(values) != len(set(values)):
                raise ValueError(f"{label} contains duplicate agent ids")
        overlap = set(self.required_agents) & set(self.excluded_agents)
        if overlap:
            raise ValueError(f"agents cannot be both required and excluded: {sorted(overlap)}")
        object.__setattr__(self, "required_agents", tuple(sorted(self.required_agents)))
        object.__setattr__(self, "excluded_agents", tuple(sorted(self.excluded_agents)))

    @property
    def constrained(self) -> bool:
        return bool(
            self.uav.constrained
            or self.ugv.constrained
            or self.required_agents
            or self.excluded_agents
        )

    def validate_scene(self, scene: Scene) -> None:
        fleet = {agent.agent_id: agent for agent in scene.fleet}
        unknown = (set(self.required_agents) | set(self.excluded_agents)) - set(fleet)
        if unknown:
            raise ResourceRequestError(f"unknown agent ids: {sorted(unknown)}")
        for platform, constraint in (
            (PlatformKind.UAV, self.uav),
            (PlatformKind.UGV, self.ugv),
        ):
            total = sum(agent.platform_kind is platform for agent in scene.fleet)
            if constraint.exact is not None and constraint.exact > total:
                raise ResourceRequestError(
                    f"{platform.value} exact count {constraint.exact} exceeds fleet size {total}"
                )
            if constraint.minimum is not None and constraint.minimum > total:
                raise ResourceRequestError(
                    f"{platform.value} minimum {constraint.minimum} exceeds fleet size {total}"
                )

    def count_for(self, platform: PlatformKind) -> CountConstraint:
        if platform is PlatformKind.UAV:
            return self.uav
        if platform is PlatformKind.UGV:
            return self.ugv
        raise ValueError(f"unsupported platform: {platform!r}")

    def to_dict(self) -> dict[str, object]:
        return {
            "uav": self.uav.to_dict(),
            "ugv": self.ugv.to_dict(),
            "required_agents": list(self.required_agents),
            "excluded_agents": list(self.excluded_agents),
        }

    @classmethod
    def from_flat_slots(cls, slots: dict[str, object]) -> ResourceRequest:
        return cls(
            uav=CountConstraint(
                exact=slots.get("uav_exact"),
                minimum=slots.get("uav_min"),
                maximum=slots.get("uav_max"),
            ),
            ugv=CountConstraint(
                exact=slots.get("ugv_exact"),
                minimum=slots.get("ugv_min"),
                maximum=slots.get("ugv_max"),
            ),
            required_agents=tuple(slots.get("required_agents") or ()),
            excluded_agents=tuple(slots.get("excluded_agents") or ()),
        )


__all__ = ["CountConstraint", "ResourceRequest", "ResourceRequestError"]
