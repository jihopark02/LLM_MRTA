"""Strict, deterministic simulated fire observation fixture (§22.2).

The latent fixture is deliberately not part of :class:`scenarios.scene.Scene`.
Loading it cannot change ``scene_hash`` and no interaction prompt can see it.
It represents a controlled experiment condition revealed only when its exact
AREA_RECON task first appears in a checkpoint's ``completed_now`` list.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from core.enums import TaskType
from interaction.audit import CheckpointAudit
from scenarios.compiler import task_id_for
from scenarios.naming import normalize_identifier
from scenarios.scene import Scene

_REQUIRED_KEYS = frozenset({"fixture_id", "zone_id", "trigger_task_id"})


@dataclass(frozen=True, slots=True)
class LatentIncidentFixture:
    fixture_id: str
    zone_id: str
    trigger_task_id: str

    def __post_init__(self) -> None:
        for label, value in (
            ("fixture_id", self.fixture_id),
            ("zone_id", self.zone_id),
            ("trigger_task_id", self.trigger_task_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{label} must be a non-empty str")


@dataclass(frozen=True, slots=True)
class FireDetectedObservation:
    fixture_id: str
    zone_id: str
    trigger_task_id: str
    detecting_agent_id: str
    simulation_time: float
    event_type: str = field(default="FIRE_DETECTED", init=False)

    def __post_init__(self) -> None:
        for label, value in (
            ("fixture_id", self.fixture_id),
            ("zone_id", self.zone_id),
            ("trigger_task_id", self.trigger_task_id),
            ("detecting_agent_id", self.detecting_agent_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{label} must be a non-empty str")
        now = self.simulation_time
        if not isinstance(now, (int, float)) or isinstance(now, bool):
            raise ValueError("simulation_time must be a finite non-negative number")
        if not math.isfinite(now) or now < 0.0:
            raise ValueError("simulation_time must be a finite non-negative number")


def _required_text(raw: Mapping, key: str) -> str:
    value = raw[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty str, got {value!r}")
    return value


def load_latent_incident_fixture(
    path: str | Path, scene: Scene
) -> LatentIncidentFixture:
    """Load one fixture and bind it to its public patrol scene.

    The object shape is exact: misspelled or future fields are rejected rather
    than silently ignored.  The trigger is derived from the zone and therefore
    cannot point at another task type or another zone.
    """
    raw = yaml.safe_load(Path(path).read_text())
    if not isinstance(raw, dict):
        raise ValueError("latent incident fixture must be a mapping")
    keys = frozenset(raw)
    if keys != _REQUIRED_KEYS:
        missing = sorted(_REQUIRED_KEYS - keys)
        extra = sorted(keys - _REQUIRED_KEYS)
        raise ValueError(f"latent fixture keys mismatch; missing={missing}, extra={extra}")

    fixture_id = _required_text(raw, "fixture_id")
    if not normalize_identifier(fixture_id):
        raise ValueError("fixture_id must have a non-empty normalized form")
    zone_id = _required_text(raw, "zone_id")
    trigger_task_id = _required_text(raw, "trigger_task_id")
    if zone_id not in scene.zones:
        raise ValueError(f"latent fixture references unknown zone: {zone_id!r}")
    expected = task_id_for(TaskType.AREA_RECON, zone_id)
    if trigger_task_id != expected:
        raise ValueError(
            f"trigger_task_id must be the zone AREA_RECON task {expected!r}, "
            f"got {trigger_task_id!r}"
        )
    return LatentIncidentFixture(fixture_id, zone_id, trigger_task_id)


@dataclass(slots=True)
class SimulatedFireSource:
    """Reveal one fixture once; reruns and later checkpoints are idempotent."""

    fixture: LatentIncidentFixture
    _emitted: bool = False

    def inspect(
        self,
        checkpoint: CheckpointAudit,
        assignments: Mapping[str, str],
    ) -> FireDetectedObservation | None:
        if self._emitted or self.fixture.trigger_task_id not in checkpoint.completed_now:
            return None
        detecting_agent = assignments.get(self.fixture.trigger_task_id)
        if not isinstance(detecting_agent, str) or not detecting_agent:
            raise ValueError("completed trigger has no recorded detecting agent")
        now = checkpoint.simulation_time
        if not isinstance(now, (int, float)) or isinstance(now, bool) or not math.isfinite(now):
            raise ValueError("checkpoint simulation_time must be finite")
        if now < 0.0:
            raise ValueError("checkpoint simulation_time must be non-negative")
        observation = FireDetectedObservation(
            fixture_id=self.fixture.fixture_id,
            zone_id=self.fixture.zone_id,
            trigger_task_id=self.fixture.trigger_task_id,
            detecting_agent_id=detecting_agent,
            simulation_time=float(now),
        )
        self._emitted = True
        return observation


__all__ = [
    "FireDetectedObservation",
    "LatentIncidentFixture",
    "SimulatedFireSource",
    "load_latent_incident_fixture",
]
