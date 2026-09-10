"""D-076: Semantic Mission IR schema — the LLM's only mission-structure output.

Strict shape checks only. Resolution against a live world is
tests/test_resolve.py; compilation is tests/test_compile_clauses.py.
"""

import pytest
from pydantic import ValidationError

from interaction.mission_ir import IncidentSelector, SemanticMissionIR, ZoneSelector
from tests.ir_fixtures import isel, mission_ir, policy, recon, response, zsel


def test_a_range_recon_with_exclusions_parses():
    ir = mission_ir(recon=(recon(range_from="A", range_to="H", exclude=("C", "F")),))
    assert ir.recon[0].zones.range_from == "A"
    assert ir.recon[0].zones.exclude == ["C", "F"]


def test_multi_clause_one_utterance():
    ir = mission_ir(
        recon=(recon(explicit=("D",)),),
        responses=(
            response("GROUND_SUPPRESSION", explicit=("FIRE_SITE_1",)),
            response("GROUND_INSPECTION", explicit=("2번",)),
        ),
    )
    assert len(ir.responses) == 2
    assert {r.response_up_to for r in ir.responses} == {
        "GROUND_SUPPRESSION", "GROUND_INSPECTION"}


def test_recent_incidents_with_spatial_pick():
    sel = isel(recency="MOST_RECENT_DETECTED", recent_count=2, spatial_pick="EASTMOST")
    assert sel.recent_count == 2 and sel.spatial_pick == "EASTMOST"


def test_zone_selector_needs_exactly_one_base():
    zsel(explicit=("A",))
    zsel(range_from="A", range_to="H")
    zsel(region="WEST")
    with pytest.raises(ValidationError):
        zsel(explicit=("A",), region="WEST")
    with pytest.raises(ValidationError):
        zsel(exclude=("C",))                 # only a modifier, no base
    with pytest.raises(ValidationError):
        zsel(range_from="A")                 # half a range


def test_incident_selector_needs_exactly_one_base():
    isel(explicit=("FIRE_SITE_1",))
    isel(deixis="거기")
    isel(recency="ALL_KNOWN")
    with pytest.raises(ValidationError):
        isel(deixis="거기", recency="ALL_KNOWN")
    with pytest.raises(ValidationError):
        isel(spatial_pick="EASTMOST")
    with pytest.raises(ValidationError):
        isel(explicit=("FIRE_SITE_1",), recent_count=2)


def test_empty_ir_is_rejected():
    with pytest.raises(ValidationError):
        mission_ir()


def test_incident_policy_alone_is_a_valid_ir():
    ir = mission_ir(incident_policy=policy("GROUND_INSPECTION"))
    assert ir.incident_policy.trigger == "FIRE_DETECTED"


def test_no_field_defaults_openai_strict_safe():
    from openai.lib._pydantic import to_strict_json_schema

    schema = to_strict_json_schema(SemanticMissionIR)
    import json
    text = json.dumps(schema)
    assert '"default"' not in text
    assert '"oneOf"' not in text
    for obj in [schema, *schema.get("$defs", {}).values()]:
        if obj.get("type") == "object":
            assert set(obj["properties"]) == set(obj["required"])


def test_extra_keys_and_loose_types_are_rejected():
    with pytest.raises(ValidationError):
        ZoneSelector(explicit=["A"], range_from=None, range_to=None, region=None,
                     exclude=[], unvisited_only=False, priority=9)
    with pytest.raises(ValidationError):
        response("AREA_RECON", explicit=("FIRE_SITE_1",))
    with pytest.raises(ValidationError):
        IncidentSelector(explicit=[], deixis=None, recency="MOST_RECENT_DETECTED",
                         recent_count="2", recent_source=None, spatial_pick=None)
