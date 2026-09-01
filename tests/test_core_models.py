"""Unit tests for core data models (RESEARCH_CONTRACT.md §6, §7). P1 gate item 1."""

import pytest

from core.agent import Agent
from core.enums import Capability, PlatformKind, TaskStatus, TaskType
from core.task import Task


def make_agent(**overrides) -> Agent:
    base = dict(
        agent_id="S1",
        platform_kind=PlatformKind.UAV,
        capabilities=frozenset({Capability.AERIAL_RECON, Capability.THERMAL_SENSOR}),
        initial_position=(0.0, 0.0),
        position=(0.0, 0.0),
        speed=5.0,
    )
    base.update(overrides)
    return Agent(**base)


def test_enums_are_plain_strings():
    # Python 3.10 str-mixin pattern: value compares equal to the bare string.
    assert Capability.AERIAL_RECON == "AERIAL_RECON"
    assert TaskType.SUPPRESSANT_DROP == "SUPPRESSANT_DROP"
    assert PlatformKind.UGV == "UGV"


def test_agent_defaults_are_independent_lists():
    a, b = make_agent(agent_id="S1"), make_agent(agent_id="S2")
    a.bundle.append("T1")
    assert b.bundle == []
    assert a.path == [] and a.current_task is None


def test_agent_has_capabilities_requires_full_subset():
    a = make_agent(capabilities=frozenset({Capability.GROUND_MOBILITY}))
    assert a.has_capabilities(frozenset({Capability.GROUND_MOBILITY}))
    assert not a.has_capabilities(
        frozenset({Capability.GROUND_MOBILITY, Capability.SUPPRESSANT_APPLICATOR})
    )
    assert a.has_capabilities(frozenset())


def test_task_construction_carries_frozenset_fields():
    t = Task(
        task_id="AREA_RECON__ZONE_A",
        task_type=TaskType.AREA_RECON,
        target="ZONE_A",
        position=(10.0, 20.0),
        priority=5,
        required_capabilities=frozenset({Capability.AERIAL_RECON}),
        eligible_platforms=frozenset({PlatformKind.UAV}),
        duration=30.0,
        status=TaskStatus.READY,
    )
    assert t.assigned_agent is None
    assert PlatformKind.UAV in t.eligible_platforms


def _task(**overrides) -> Task:
    base = dict(
        task_id="T1",
        task_type=TaskType.AREA_RECON,
        target="ZONE_A",
        position=(0.0, 0.0),
        priority=1,
        required_capabilities=frozenset({Capability.AERIAL_RECON}),
        eligible_platforms=frozenset({PlatformKind.UAV}),
        duration=10.0,
        status=TaskStatus.READY,
    )
    base.update(overrides)
    return Task(**base)


@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf")])
def test_task_duration_must_be_finite_positive(bad):
    with pytest.raises(ValueError, match="duration"):
        _task(duration=bad)


@pytest.mark.parametrize("bad", [0, 11, -3, True, 5.8, "7"])
def test_task_priority_must_be_int_1_to_10(bad):
    with pytest.raises(ValueError, match="priority"):
        _task(priority=bad)


@pytest.mark.parametrize("good", [1, 10])
def test_task_priority_boundaries_accepted(good):
    assert _task(priority=good).priority == good


def test_dataclass_slots_reject_unknown_attributes():
    a = make_agent()
    with pytest.raises(AttributeError):
        a.access_node = "N1"  # platform-specific config must not leak into core Agent
