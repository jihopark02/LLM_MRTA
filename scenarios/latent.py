"""Strict, deterministic simulated fire observation fixture (§22.2).

The latent fixture is deliberately not part of :class:`scenarios.scene.Scene`.
Loading it cannot change ``scene_hash`` and no interaction prompt can see it.
It represents a controlled experiment condition revealed only when its exact
AREA_RECON task first appears in a checkpoint's ``completed_now`` list.
"""

from __future__ import annotations

import math
import random
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


_FIELD_REQUIRED_KEYS = frozenset({"field_id", "seed", "count"})
_FIELD_OPTIONAL_KEYS = frozenset({"candidate_zones"})


@dataclass(frozen=True, slots=True)
class LatentFireField:
    """A seeded set of latent fires: the world is fixed, only the zones burn.

    ``fixtures`` is ordered by zone id and each entry is an ordinary
    :class:`LatentIncidentFixture`, so the field composes with everything that
    already consumes a single fixture.
    """

    field_id: str
    seed: int
    fixtures: tuple[LatentIncidentFixture, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.field_id, str) or not self.field_id.strip():
            raise ValueError("field_id must be a non-empty str")
        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise ValueError("seed must be an int")
        if not self.fixtures:
            raise ValueError("a latent fire field needs at least one fixture")
        zones = [fixture.zone_id for fixture in self.fixtures]
        if len(set(zones)) != len(zones):
            raise ValueError("latent fire field has duplicate zones")

    @property
    def zone_ids(self) -> tuple[str, ...]:
        return tuple(fixture.zone_id for fixture in self.fixtures)


def load_latent_fire_field(path: str | Path, scene: Scene) -> LatentFireField:
    """Load a pinned field spec and resolve it against its patrol scene.

    ``random.Random(seed).sample`` over the sorted candidate pool makes the
    chosen zones a deterministic function of (seed, spec, scene).  Nothing here
    touches the scene, so ``scene_hash`` is unaffected and no prompt can see it.
    """
    raw = yaml.safe_load(Path(path).read_text())
    if not isinstance(raw, dict):
        raise ValueError("latent fire field spec must be a mapping")
    keys = frozenset(raw)
    missing = sorted(_FIELD_REQUIRED_KEYS - keys)
    extra = sorted(keys - _FIELD_REQUIRED_KEYS - _FIELD_OPTIONAL_KEYS)
    if missing or extra:
        raise ValueError(
            f"latent fire field keys mismatch; missing={missing}, extra={extra}"
        )

    field_id = _required_text(raw, "field_id")
    if not normalize_identifier(field_id):
        raise ValueError("field_id must have a non-empty normalized form")
    seed = raw["seed"]
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError(f"seed must be an int, got {seed!r}")
    count = raw["count"]
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise ValueError(f"count must be an int >= 1, got {count!r}")

    if "candidate_zones" in raw:
        candidates = raw["candidate_zones"]
        if (
            not isinstance(candidates, list)
            or not candidates
            or not all(isinstance(zone, str) and zone.strip() for zone in candidates)
        ):
            raise ValueError("candidate_zones must be a non-empty list of zone ids")
        if len(set(candidates)) != len(candidates):
            raise ValueError("candidate_zones has duplicate entries")
        unknown = sorted(set(candidates) - set(scene.zones))
        if unknown:
            raise ValueError(f"candidate_zones references unknown zones: {unknown}")
        pool = sorted(candidates)
    else:
        pool = sorted(scene.zones)

    if count > len(pool):
        raise ValueError(
            f"count {count} exceeds the candidate zone pool size {len(pool)}"
        )

    chosen = sorted(random.Random(seed).sample(pool, count))
    fixtures = tuple(
        LatentIncidentFixture(
            fixture_id=f"{field_id}-{zone_id}",
            zone_id=zone_id,
            trigger_task_id=task_id_for(TaskType.AREA_RECON, zone_id),
        )
        for zone_id in chosen
    )
    return LatentFireField(field_id=field_id, seed=seed, fixtures=fixtures)


@dataclass(slots=True)
class SimulatedFireField:
    """Reveal every fixture in a field once, zone-id ordered per checkpoint."""

    fire_field: LatentFireField
    _sources: tuple[SimulatedFireSource, ...] | None = None

    def __post_init__(self) -> None:
        if self._sources is None:
            self._sources = tuple(
                SimulatedFireSource(fixture) for fixture in self.fire_field.fixtures
            )

    def inspect(
        self,
        checkpoint: CheckpointAudit,
        assignments: Mapping[str, str],
    ) -> tuple[FireDetectedObservation, ...]:
        revealed = [
            observation
            for source in self._sources
            if (observation := source.inspect(checkpoint, assignments)) is not None
        ]
        revealed.sort(key=lambda observation: observation.zone_id)
        return tuple(revealed)


__all__ = [
    "FireDetectedObservation",
    "LatentFireField",
    "LatentIncidentFixture",
    "SimulatedFireField",
    "SimulatedFireSource",
    "load_latent_fire_field",
    "load_latent_incident_fixture",
]
