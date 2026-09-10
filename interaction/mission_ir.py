"""Semantic Mission IR — the LLM's only mission-structure output (D-076, §18.3).

The interaction LLM no longer emits task instances, target ids, dependency
edges, coordinates, priority, capability, agent, allocation or MissionPatch
ops. It emits **generic language operators** describing *what the operator
meant*; a deterministic Clause Resolver (`interaction/resolve.py`) turns each
operator into a concrete target set against the current Scene / MissionState /
event_log, and a deterministic Mission Compiler
(`interaction/compile_clauses.py`) builds the canonical graph or additive
patch.

The IR carries no ``operation`` field: whether the same IR compiles into a new
graph (`NEW_MISSION`) or an additive patch on the current graph
(`UPDATE_MISSION`) is decided by the dialogue-act kind in the deterministic
layer, never by the model.

Shape note: no discriminated unions anywhere (OpenAI structured output rejects
nested ``oneOf`` — D-034). A mission is a list of zone-recon clauses plus a
list of incident-response clauses; every selector is a flat object of scalars
and string tuples. ``extra="forbid"`` + ``strict=True`` on every model, as in
``llm/schemas.py`` and ``interaction/schemas.py``.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

Region = Literal["NORTH", "SOUTH", "EAST", "WEST"]
SpatialPick = Literal["EASTMOST", "WESTMOST", "NORTHMOST", "SOUTHMOST"]
Recency = Literal["MOST_RECENT_DETECTED", "PREVIOUS_DETECTED", "ALL_KNOWN"]
ResponseDepth = Literal["GROUND_INSPECTION", "GROUND_SUPPRESSION"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ZoneSelector(_StrictModel):
    """Which zones a recon clause covers — as language operators, not zone ids.

    Exactly one *base* selector must be given (``explicit`` phrases, a
    ``range_from``/``range_to`` pair, or a ``region``); ``exclude`` and
    ``unvisited_only`` are modifiers applied by the resolver afterwards.
    """

    explicit: tuple[str, ...] = ()          # raw phrases: "A", "A 구역", "ZONE_A"
    range_from: str | None = None           # "A"  — resolved over Scene.zones key order
    range_to: str | None = None             # "H"
    region: Region | None = None            # scene-bbox half-plane (§18.3)
    exclude: tuple[str, ...] = ()            # raw phrases removed from the base set
    unvisited_only: bool = False             # drop zones whose AREA_RECON is COMPLETED

    @model_validator(mode="after")
    def _one_base_selector(self):
        has_range = self.range_from is not None or self.range_to is not None
        bases = (bool(self.explicit), has_range, self.region is not None)
        if sum(bases) != 1:
            raise ValueError(
                "a ZoneSelector needs exactly one base selector "
                "(explicit / range / region)"
            )
        if has_range and (self.range_from is None or self.range_to is None):
            raise ValueError("a range needs both range_from and range_to")
        return self


class IncidentSelector(_StrictModel):
    """Which incidents a response clause targets — as language operators.

    Exactly one base selector: ``explicit`` phrases, a ``deixis`` phrase
    ("거기" / "아까 그곳"), or a ``recency`` bucket. ``recent_count`` refines a
    recency bucket; ``spatial_pick`` reduces whatever set results to one
    entity (or clarifies on a tie).
    """

    explicit: tuple[str, ...] = ()
    deixis: str | None = None               # "거기", "아까 그곳"
    recency: Recency | None = None
    recent_count: int | None = None         # e.g. "방금 발견한 두 화재" -> 2
    spatial_pick: SpatialPick | None = None

    @model_validator(mode="after")
    def _one_base_selector(self):
        bases = (bool(self.explicit), self.deixis is not None, self.recency is not None)
        if sum(bases) != 1:
            raise ValueError(
                "an IncidentSelector needs exactly one base selector "
                "(explicit / deixis / recency)"
            )
        if self.recent_count is not None:
            if self.recency is None:
                raise ValueError("recent_count only applies with a recency selector")
            if self.recent_count < 1:
                raise ValueError("recent_count must be >= 1")
        return self


class ReconClause(_StrictModel):
    zones: ZoneSelector


class ResponseClause(_StrictModel):
    incidents: IncidentSelector
    response_up_to: ResponseDepth


class ConditionalPolicy(_StrictModel):
    """P12 future-incident policy — carried through unchanged (§22)."""

    trigger: Literal["FIRE_DETECTED"] = "FIRE_DETECTED"
    response_up_to: ResponseDepth


class SemanticMissionIR(_StrictModel):
    """One utterance's worth of mission semantics. Multi-clause: several recon
    and/or response clauses in one turn compile to one atomic result."""

    recon: tuple[ReconClause, ...] = ()
    responses: tuple[ResponseClause, ...] = ()
    incident_policy: ConditionalPolicy | None = None

    @model_validator(mode="after")
    def _not_empty(self):
        if not (self.recon or self.responses or self.incident_policy):
            raise ValueError(
                "a SemanticMissionIR needs at least one recon / response clause "
                "or an incident_policy"
            )
        return self


__all__ = [
    "Region",
    "SpatialPick",
    "Recency",
    "ResponseDepth",
    "ZoneSelector",
    "IncidentSelector",
    "ReconClause",
    "ResponseClause",
    "ConditionalPolicy",
    "SemanticMissionIR",
]
