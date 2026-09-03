"""Registering an operator-reported incident (RESEARCH_CONTRACT.md §18.10).

This is the only way a new incident enters the system (§18.1) — there is no
perception and nothing infers that a fire exists. The operator names a zone;
everything else is deterministic:

- the id is generated, never taken from the model (D-027 removed the ``label``
  slot precisely because a model-authored id can collide or be hallucinated),
- the priority is a fixed constant, not inferred from urgency wording,
- the position and the UGV access node come from that zone's predefined
  response point, so no coordinate is ever invented.

The call is a transaction on the scene: it returns a NEW ``Scene`` with a new
``incidents`` dict and leaves the original untouched. ``zones``, ``route_graph``
and ``fleet`` are shared structurally — they are treated as immutable for the
whole planning session (§18.8), and the tests assert the original scene's hash
and fields are unchanged after a call.
"""

import re
from collections.abc import Iterable
from dataclasses import replace

from core.enums import IncidentStatus
from scenarios.scene import Incident, Scene

#: §18.10. Operator reports do not carry urgency — priority is not something
#: the LLM gets to decide, even indirectly. Matches FIRE_SITE_2's severity.
REPORTED_INCIDENT_PRIORITY = 7

_ID_PREFIX = "FIRE_SITE_"
_ID_PATTERN = re.compile(rf"^{_ID_PREFIX}([1-9][0-9]*)$")


def next_incident_id(existing: Iterable[str]) -> str:
    """``FIRE_SITE_<highest + 1>`` (§18.10).

    Only ids matching the canonical pattern contribute to the number, so a
    hand-written or legacy id cannot skew the counter — but the result is then
    checked against *every* existing id, malformed ones included, because
    uniqueness is what actually matters.
    """
    known = set(existing)
    highest = max(
        (int(m.group(1)) for m in (_ID_PATTERN.fullmatch(i) for i in known) if m),
        default=0,
    )
    candidate = f"{_ID_PREFIX}{highest + 1}"
    if candidate in known:  # unreachable via the pattern above; guards changes to it
        raise ValueError(f"generated incident id collides with an existing one: {candidate}")
    return candidate


def register_incident(scene: Scene, zone_id: str) -> tuple[Scene, str]:
    """Add an operator-reported incident in ``zone_id``.

    Returns the new scene and the generated incident id. Raises ``ValueError``
    for an unknown zone, in which case nothing is built and ``scene`` is
    untouched.
    """
    if zone_id not in scene.zones:
        raise ValueError(f"unknown zone: {zone_id!r}")

    zone = scene.zones[zone_id]
    incident_id = next_incident_id(scene.incidents)
    incident = Incident(
        incident_id=incident_id,
        zone=zone_id,
        priority=REPORTED_INCIDENT_PRIORITY,
        position=zone.reported_incident_position,
        access_node=zone.reported_incident_access_node,
        status=IncidentStatus.RESPONSE_REQUIRED,
    )
    # A new incidents dict; zones / route_graph / fleet stay shared and are
    # treated as immutable for the session (§18.8).
    return replace(scene, incidents={**scene.incidents, incident_id: incident}), incident_id


__all__ = ["REPORTED_INCIDENT_PRIORITY", "next_incident_id", "register_incident"]
