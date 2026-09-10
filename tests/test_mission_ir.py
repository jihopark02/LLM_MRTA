"""D-076: Semantic Mission IR schema — the LLM's only mission-structure output.

Strict shape checks only. Resolution against a live world is
tests/test_resolve.py; compilation is tests/test_compile_clauses.py.
"""

import pytest
from pydantic import ValidationError

from interaction.mission_ir import (
    ConditionalPolicy,
    IncidentSelector,
    ReconClause,
    ResponseClause,
    SemanticMissionIR,
    ZoneSelector,
)


def test_a_range_recon_with_exclusions_parses():
    ir = SemanticMissionIR(
        recon=(ReconClause(zones=ZoneSelector(
            range_from="A", range_to="H", exclude=("C", "F"))),),
    )
    assert ir.recon[0].zones.range_from == "A"
    assert ir.recon[0].zones.exclude == ("C", "F")


def test_multi_clause_one_utterance():
    ir = SemanticMissionIR(
        recon=(ReconClause(zones=ZoneSelector(explicit=("D",), region=None)),),
        responses=(
            ResponseClause(incidents=IncidentSelector(explicit=("FIRE_SITE_1",)),
                           response_up_to="GROUND_SUPPRESSION"),
            ResponseClause(incidents=IncidentSelector(explicit=("2번",)),
                           response_up_to="GROUND_INSPECTION"),
        ),
    )
    assert len(ir.responses) == 2
    assert {r.response_up_to for r in ir.responses} == {
        "GROUND_SUPPRESSION", "GROUND_INSPECTION"}


def test_recent_incidents_with_spatial_pick():
    sel = IncidentSelector(recency="MOST_RECENT_DETECTED", recent_count=2,
                           spatial_pick="EASTMOST")
    assert sel.recent_count == 2 and sel.spatial_pick == "EASTMOST"


def test_zone_selector_needs_exactly_one_base():
    ZoneSelector(explicit=("A",))                       # ok
    ZoneSelector(range_from="A", range_to="H")          # ok
    ZoneSelector(region="WEST")                         # ok
    with pytest.raises(ValidationError):
        ZoneSelector(explicit=("A",), region="WEST")    # two bases
    with pytest.raises(ValidationError):
        ZoneSelector(exclude=("C",))                    # only a modifier, no base
    with pytest.raises(ValidationError):
        ZoneSelector(range_from="A")                    # half a range


def test_incident_selector_needs_exactly_one_base():
    IncidentSelector(explicit=("FIRE_SITE_1",))
    IncidentSelector(deixis="거기")
    IncidentSelector(recency="ALL_KNOWN")
    with pytest.raises(ValidationError):
        IncidentSelector(deixis="거기", recency="ALL_KNOWN")
    with pytest.raises(ValidationError):
        IncidentSelector(spatial_pick="EASTMOST")            # no base
    with pytest.raises(ValidationError):
        IncidentSelector(explicit=("FIRE_SITE_1",), recent_count=2)  # count w/o recency


def test_empty_ir_is_rejected():
    with pytest.raises(ValidationError):
        SemanticMissionIR()


def test_incident_policy_alone_is_a_valid_ir():
    ir = SemanticMissionIR(incident_policy=ConditionalPolicy(
        response_up_to="GROUND_INSPECTION"))
    assert ir.incident_policy.trigger == "FIRE_DETECTED"


def test_extra_keys_and_loose_types_are_rejected():
    with pytest.raises(ValidationError):
        ZoneSelector(explicit=("A",), priority=9)            # extra=forbid
    with pytest.raises(ValidationError):
        ResponseClause(incidents=IncidentSelector(explicit=("FIRE_SITE_1",)),
                       response_up_to="AREA_RECON")          # not a workflow depth
    with pytest.raises(ValidationError):
        IncidentSelector(recency="MOST_RECENT_DETECTED", recent_count="2")  # strict int
