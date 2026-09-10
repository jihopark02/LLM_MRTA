"""Test-only builders for the Semantic Mission IR (D-076).

The runtime IR schema has no field defaults (it is a live structured-output
schema — see interaction/mission_ir.py). These helpers fill the "absent"
values so a test can name only the operator it cares about. NOT a runtime
compatibility layer: the production wire boundary accepts the D-076 contract
schema only.
"""

from interaction.mission_ir import (
    ConditionalPolicy,
    IncidentSelector,
    ReconClause,
    ResponseClause,
    SemanticMissionIR,
    ZoneSelector,
)


def zsel(*, explicit=(), range_from=None, range_to=None, region=None,
         exclude=(), unvisited_only=False) -> ZoneSelector:
    return ZoneSelector(
        explicit=list(explicit), range_from=range_from, range_to=range_to,
        region=region, exclude=list(exclude), unvisited_only=unvisited_only,
    )


def isel(*, explicit=(), deixis=None, recency=None, recent_count=None,
         recent_source=None, spatial_pick=None) -> IncidentSelector:
    return IncidentSelector(
        explicit=list(explicit), deixis=deixis, recency=recency,
        recent_count=recent_count, recent_source=recent_source,
        spatial_pick=spatial_pick,
    )


def recon(**zone_kw) -> ReconClause:
    return ReconClause(zones=zsel(**zone_kw))


def response(response_up_to, **incident_kw) -> ResponseClause:
    return ResponseClause(incidents=isel(**incident_kw), response_up_to=response_up_to)


def mission_ir(*, recon=(), responses=(), incident_policy=None) -> SemanticMissionIR:
    return SemanticMissionIR(
        recon=list(recon), responses=list(responses), incident_policy=incident_policy,
    )


def policy(response_up_to) -> ConditionalPolicy:
    return ConditionalPolicy(trigger="FIRE_DETECTED", response_up_to=response_up_to)


def recon_ir(**zone_kw) -> SemanticMissionIR:
    """A one-recon-clause mission IR (name only the zone operator under test)."""
    return mission_ir(recon=(recon(**zone_kw),))


def response_ir(response_up_to="GROUND_SUPPRESSION", **incident_kw) -> SemanticMissionIR:
    """A one-response-clause mission IR."""
    return mission_ir(responses=(response(response_up_to, **incident_kw),))


def new_mission_wire(mission: SemanticMissionIR | None = None, **slots):
    """Wire envelope for NEW_MISSION. Default mission = suppress FIRE_SITE_1 —
    the D-076 equivalent of the old ``wire_intent("NEW_MISSION")`` default."""
    from interaction.schemas import wire_intent

    return wire_intent(
        "NEW_MISSION",
        mission=mission or response_ir("GROUND_SUPPRESSION", explicit=("FIRE_SITE_1",)),
        **slots,
    )


def update_mission_wire(mission: SemanticMissionIR, **slots):
    from interaction.schemas import wire_intent

    return wire_intent("UPDATE_MISSION", mission=mission, **slots)
