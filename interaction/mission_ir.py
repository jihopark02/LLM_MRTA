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

Schema shape — this is a live LLM structured-output schema, so it follows the
same rules as ``llm/schemas.py`` / ``interaction/schemas.py``: **no field
defaults** (every property is ``required``; "absent" is an empty list or an
explicit ``null``), no discriminated unions (OpenAI rejects nested ``oneOf`` —
D-034), ``extra="forbid"`` + ``strict=True``. Construction in tests goes
through ``tests`` helpers; nothing in the codebase builds an IR by hand on the
runtime path.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

Region = Literal["NORTH", "SOUTH", "EAST", "WEST"]
SpatialPick = Literal["EASTMOST", "WESTMOST", "NORTHMOST", "SOUTHMOST"]
Recency = Literal["MOST_RECENT_DETECTED", "PREVIOUS_DETECTED", "ALL_KNOWN"]
RecentSource = Literal["SENSOR", "OPERATOR", "ANY"]
ResponseDepth = Literal["GROUND_INSPECTION", "GROUND_SUPPRESSION"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ZoneSelector(_StrictModel):
    """Which zones a recon clause covers — as language operators, not zone ids.

    Exactly one *base* selector must be given (non-empty ``explicit`` phrases, a
    ``range_from``/``range_to`` pair, or a ``region``); ``exclude`` and
    ``unvisited_only`` are modifiers the resolver applies afterwards.
    """

    explicit: list[str]                      # raw phrases ("A", "A 구역", "ZONE_A"); [] if unused
    range_from: str | None                   # "A" — resolved over Scene.zones key order
    range_to: str | None                     # "H"
    region: Region | None                    # scene-bbox half-plane (§18.3)
    exclude: list[str]                        # raw phrases removed from the base set; [] if none
    unvisited_only: bool                      # drop zones whose AREA_RECON is COMPLETED

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

    Exactly one base selector: non-empty ``explicit`` phrases, a ``deixis``
    phrase ("거기" / "아까 그곳"), or a ``recency`` bucket. ``recent_count`` /
    ``recent_source`` refine a recency bucket; ``spatial_pick`` reduces whatever
    set results to one entity (or clarifies on a tie).
    """

    explicit: list[str]                       # [] if unused
    deixis: str | None
    recency: Recency | None
    recent_count: int | None                  # "방금 발견한 두 화재" -> 2
    recent_source: RecentSource | None        # SENSOR / OPERATOR / ANY (null == ANY)
    spatial_pick: SpatialPick | None

    @model_validator(mode="after")
    def _one_base_selector(self):
        bases = (bool(self.explicit), self.deixis is not None, self.recency is not None)
        if sum(bases) != 1:
            raise ValueError(
                "an IncidentSelector needs exactly one base selector "
                "(explicit / deixis / recency)"
            )
        for name, value in (("recent_count", self.recent_count),
                            ("recent_source", self.recent_source)):
            if value is not None and self.recency is None:
                raise ValueError(f"{name} only applies with a recency selector")
        if self.recent_count is not None and self.recent_count < 1:
            raise ValueError("recent_count must be >= 1")
        return self


class ReconClause(_StrictModel):
    zones: ZoneSelector


class ResponseClause(_StrictModel):
    incidents: IncidentSelector
    response_up_to: ResponseDepth


class ConditionalPolicy(_StrictModel):
    """P12 future-incident policy — carried through unchanged (§22)."""

    trigger: Literal["FIRE_DETECTED"]
    response_up_to: ResponseDepth


class SemanticMissionIR(_StrictModel):
    """One utterance's worth of mission semantics. Multi-clause: several recon
    and/or response clauses in one turn compile to one atomic result."""

    recon: list[ReconClause]                  # [] if the turn adds no recon
    responses: list[ResponseClause]           # [] if the turn adds no response
    incident_policy: ConditionalPolicy | None

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
    "RecentSource",
    "ResponseDepth",
    "ZoneSelector",
    "IncidentSelector",
    "ReconClause",
    "ResponseClause",
    "ConditionalPolicy",
    "SemanticMissionIR",
]
