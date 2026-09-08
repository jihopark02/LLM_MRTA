"""P12.1 mission-level contingency boundary (§22.1)."""

import pytest

from core.enums import TaskType
from interaction.directive import MissionDirective


@pytest.mark.parametrize(
    "step",
    [
        "GROUND_INSPECTION",
        "GROUND_SUPPRESSION",
    ],
)
def test_every_canonical_response_prefix_is_representable(step):
    directive = MissionDirective.from_slot(step)
    assert directive.incident_response_up_to is TaskType(step)
    assert directive.to_dict() == {"incident_response_up_to": step}


def test_no_conditional_phrase_means_no_policy():
    assert MissionDirective.from_slot(None) == MissionDirective()


@pytest.mark.parametrize("bad", ["AREA_RECON", "WATER_LOAD", "", "ground_suppression"])
def test_non_workflow_policy_values_fail_closed(bad):
    with pytest.raises(ValueError):
        MissionDirective.from_slot(bad)
