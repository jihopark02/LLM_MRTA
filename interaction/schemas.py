"""Operator intent schemas for the planning session (RESEARCH_CONTRACT.md §18).

D-076: in one structured-output call the interaction LLM classifies the
utterance into a dialogue act and — for ``NEW_MISSION`` / ``UPDATE_MISSION`` —
emits a ``SemanticMissionIR`` of generic language operators (`interaction/
mission_ir.py`). It never emits task/edge lists, target ids, coordinates,
priority, capability, agent, allocation, a MissionPatch, or a clarification;
the deterministic Resolver + Compiler build the graph/patch and the grounder
owns clarification (§18.5). ``REPORT_INCIDENT`` keeps its ``zone_ref`` /
``response_up_to`` slots and P13 keeps the resource slots.

Slot extraction may be partial: "불이 났어" with no location is a
``REPORT_INCIDENT`` with ``zone_ref=None``; the grounder turns that into a
clarification. ``extra="forbid"`` + ``strict=True`` on every model, no field
defaults on the wire form (OpenAI strict structured output — as in
``llm/schemas.py``).
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from interaction.mission_ir import SemanticMissionIR
from interaction.resources import ResourceRequest


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


#: The four §4 workflow steps an UPDATE may ask for. ``AREA_RECON`` is not a
#: workflow step (§4) and is rejected at the schema level.
UpToStep = Literal[
    "GROUND_INSPECTION",
    "GROUND_SUPPRESSION",
]


class NewMissionIntent(_StrictModel):
    """Create the first mission (D-076). ``mission`` is the Semantic Mission IR —
    generic language operators only; the deterministic Resolver/Compiler build
    the graph. A future-incident policy, if any, rides inside
    ``mission.incident_policy``."""

    kind: Literal["NEW_MISSION"]
    mission: SemanticMissionIR
    resources: "ResourceRequestSchema | None" = None


class ResourceRequestSchema(_StrictModel):
    """Strict LLM-facing form of the P13 mission resource request."""

    uav_exact: int | None = None
    uav_min: int | None = None
    uav_max: int | None = None
    ugv_exact: int | None = None
    ugv_min: int | None = None
    ugv_max: int | None = None
    required_agents: tuple[str, ...] = ()
    excluded_agents: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _valid_domain_shape(self):
        self.to_domain()
        return self

    def to_domain(self) -> ResourceRequest:
        return ResourceRequest.from_flat_slots(self.model_dump())


class ReportIncidentIntent(_StrictModel):
    """The operator reports a new incident — the only NL route by which an
    incident enters the system (§18.1). No ``label`` (ids are generated
    deterministically) and no urgency slot (priority is fixed, §18.10)."""

    kind: Literal["REPORT_INCIDENT"]
    zone_ref: str | None = None  # raw phrase; grounder matches zone_id + aliases
    response_up_to: UpToStep | None = None
    resources: "ResourceRequestSchema | None" = None


class UpdateResourcesIntent(_StrictModel):
    """Atomically replace the active mission's complete resource policy."""

    kind: Literal["UPDATE_RESOURCES"]
    resources: ResourceRequestSchema


class UpdateMissionIntent(_StrictModel):
    """Edit the running mission (D-076). Same ``SemanticMissionIR`` payload as
    ``NEW_MISSION`` — the deterministic layer compiles it into an *additive*
    patch against the current graph instead of a fresh graph. Multi-clause: one
    utterance may add recon and several incident responses at once."""

    kind: Literal["UPDATE_MISSION"]
    mission: SemanticMissionIR


class QueryStatusIntent(_StrictModel):
    """Read-only question about the current plan/state. Never mutates (§18.4)."""

    kind: Literal["QUERY_STATUS"]
    about: Literal["agents", "tasks", "incidents", "mission"] = "mission"
    target_phrase: str | None = None  # e.g. "그 화재" — goes through the grounder


class UnsupportedIntent(_StrictModel):
    """Out of scope (§18.2). ``note`` is for the audit log only — the UI answers
    with a fixed template and never shows model-authored free text."""

    kind: Literal["UNSUPPORTED"]
    note: str = ""


OperatorIntent = Annotated[
    NewMissionIntent
    | ReportIncidentIntent
    | UpdateResourcesIntent
    | UpdateMissionIntent
    | QueryStatusIntent
    | UnsupportedIntent,
    Field(discriminator="kind"),
]


class IntentEnvelope(_StrictModel):
    """Structured-output root. The backend needs an object at the top level, so
    the discriminated union is nested under one key."""

    intent: OperatorIntent


class IntentWireEnvelope(_StrictModel):
    """OpenAI-compatible flat transport schema (D-034).

    OpenAI structured output rejects the nested ``oneOf`` emitted by the
    discriminated union above. Every wire key is required but nullable so the
    generated JSON Schema has one object shape. A cross-field check then
    restores the kind/slot boundary before conversion to ``IntentEnvelope``.
    """

    kind: Literal[
        "NEW_MISSION",
        "REPORT_INCIDENT",
        "UPDATE_RESOURCES",
        "UPDATE_MISSION",
        "QUERY_STATUS",
        "UNSUPPORTED",
    ]
    # D-076: non-null iff kind in {NEW_MISSION, UPDATE_MISSION}
    mission: SemanticMissionIR | None
    zone_ref: str | None
    target_phrase: str | None             # QUERY_STATUS referent, e.g. "그 화재"
    response_up_to: UpToStep | None
    about: Literal["agents", "tasks", "incidents", "mission"] | None
    note: str | None
    uav_exact: int | None
    uav_min: int | None
    uav_max: int | None
    ugv_exact: int | None
    ugv_min: int | None
    ugv_max: int | None
    required_agents: list[str] | None
    excluded_agents: list[str] | None

    @model_validator(mode="after")
    def _kind_owns_non_null_slots(self):
        _RES = {"uav_exact", "uav_min", "uav_max", "ugv_exact", "ugv_min", "ugv_max",
                "required_agents", "excluded_agents"}
        allowed = {
            "NEW_MISSION": {"mission", *_RES},
            "UPDATE_MISSION": {"mission"},
            "REPORT_INCIDENT": {"zone_ref", "response_up_to", *_RES},
            "UPDATE_RESOURCES": set(_RES),
            "QUERY_STATUS": {"target_phrase", "about"},
            "UNSUPPORTED": {"note"},
        }[self.kind]
        values = {
            "zone_ref": self.zone_ref,
            "target_phrase": self.target_phrase,
            "response_up_to": self.response_up_to,
            "about": self.about,
            "note": self.note,
            "uav_exact": self.uav_exact,
            "uav_min": self.uav_min,
            "uav_max": self.uav_max,
            "ugv_exact": self.ugv_exact,
            "ugv_min": self.ugv_min,
            "ugv_max": self.ugv_max,
            "required_agents": self.required_agents,
            "excluded_agents": self.excluded_agents,
        }
        unexpected = sorted(
            key for key, value in values.items() if value is not None and key not in allowed
        )
        if unexpected:
            raise ValueError(f"{self.kind} cannot populate slots: {', '.join(unexpected)}")
        # D-076 S1: the two mission-editing acts require the IR; no one else may carry it.
        mission_act = self.kind in {"NEW_MISSION", "UPDATE_MISSION"}
        if mission_act and self.mission is None:
            raise ValueError(f"{self.kind} requires a mission (Semantic Mission IR)")
        if not mission_act and self.mission is not None:
            raise ValueError(f"{self.kind} cannot carry a mission")
        if self.kind in {"NEW_MISSION", "REPORT_INCIDENT", "UPDATE_RESOURCES"}:
            ResourceRequest.from_flat_slots(values)
        return self

    def to_internal(self) -> IntentEnvelope:
        allowed = {
            "NEW_MISSION": ("mission",),
            "UPDATE_MISSION": ("mission",),
            "REPORT_INCIDENT": ("zone_ref", "response_up_to"),
            "UPDATE_RESOURCES": (),
            "QUERY_STATUS": ("target_phrase", "about"),
            "UNSUPPORTED": ("note",),
        }[self.kind]
        payload = {"kind": self.kind}
        payload.update(
            {
                key: value
                for key in allowed
                if (value := getattr(self, key)) is not None
            }
        )
        if self.kind in {"NEW_MISSION", "REPORT_INCIDENT", "UPDATE_RESOURCES"}:
            resource_values = {
                key: getattr(self, key)
                for key in (
                    "uav_exact",
                    "uav_min",
                    "uav_max",
                    "ugv_exact",
                    "ugv_min",
                    "ugv_max",
                    "required_agents",
                    "excluded_agents",
                )
            }
            if self.kind == "UPDATE_RESOURCES" or any(
                value is not None for value in resource_values.values()
            ):
                payload["resources"] = ResourceRequestSchema.model_validate(
                    {
                        **resource_values,
                        "required_agents": tuple(resource_values["required_agents"] or ()),
                        "excluded_agents": tuple(resource_values["excluded_agents"] or ()),
                    }
                )
        return IntentEnvelope.model_validate({"intent": payload})


def wire_intent(kind: str, **slots) -> IntentWireEnvelope:
    """Test/demo helper that still crosses the exact live wire boundary.

    D-076: for NEW_MISSION / UPDATE_MISSION pass ``mission=<SemanticMissionIR>``
    (build one with ``tests.ir_fixtures``)."""
    payload = {
        "kind": kind,
        "mission": None,
        "zone_ref": None,
        "target_phrase": None,
        "response_up_to": None,
        "about": None,
        "note": None,
        "uav_exact": None,
        "uav_min": None,
        "uav_max": None,
        "ugv_exact": None,
        "ugv_min": None,
        "ugv_max": None,
        "required_agents": None,
        "excluded_agents": None,
    }
    payload.update(slots)
    return IntentWireEnvelope.model_validate(payload)


__all__ = [
    "UpToStep",
    "NewMissionIntent",
    "ResourceRequestSchema",
    "ReportIncidentIntent",
    "UpdateResourcesIntent",
    "UpdateMissionIntent",
    "QueryStatusIntent",
    "UnsupportedIntent",
    "OperatorIntent",
    "IntentEnvelope",
    "IntentWireEnvelope",
    "wire_intent",
]
