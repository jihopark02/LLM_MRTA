"""Shared deterministic entity-name normalisation (contract §18.10).

Incident identifiers and zone references intentionally use different rules:
only zone phrases may drop the Korean suffixes ``구역`` and ``지역``.  Keeping
these functions below ``interaction`` lets both the scene loader and grounder
use the same boundary without reversing the dependency direction.
"""

_ZONE_SUFFIXES = ("구역", "지역")
_ZONE_LOCATIVE_PARTICLES = ("에서", "에")


def normalize_identifier(text: str) -> str:
    """Uppercase ``text`` and retain only alphanumeric characters."""
    return "".join(ch for ch in text.strip().upper() if ch.isalnum())


def normalize_zone_ref(text: str) -> str:
    """Normalise a zone phrase with one locative and one zone suffix."""
    stripped = text.strip()
    for particle in _ZONE_LOCATIVE_PARTICLES:
        if stripped.endswith(particle):
            stripped = stripped[: -len(particle)].rstrip()
            break
    for suffix in _ZONE_SUFFIXES:
        if stripped.endswith(suffix):
            stripped = stripped[: -len(suffix)].rstrip()
            break
    return normalize_identifier(stripped)


__all__ = ["normalize_identifier", "normalize_zone_ref"]
