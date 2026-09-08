"""Operator intent schemas for the planning session (RESEARCH_CONTRACT.md §18).

The interaction LLM classifies the utterance into one of the five supported
dialogue acts (§18.2) and extracts bounded slots. P13 permits agent-class,
count, include and exclude constraints on ``NEW_MISSION``; these are not
task-to-agent assignments. It never emits a clarification, MissionPatch,
task list, priority or coordinate. For ``NEW_MISSION`` task/edge generation is the existing RQ1
``llm.pipeline.generate_mission`` on the raw utterance (§12). P12 adds one
mission-level slot beside that graph: the canonical response step for a future
detected or reported incident. It cannot name a future target or an agent.

Slot extraction may be partial: every slot is optional, so "불이 났어" with no
location is a ``REPORT_INCIDENT`` with ``zone_ref=None``. Turning a missing or
ambiguous slot into ``CLARIFICATION_REQUIRED`` is the deterministic grounder's
job (§18.5), never the model's — there is deliberately no clarification member
in this union.

``extra="forbid"`` + ``strict=True`` on every model, as in ``llm/schemas.py``:
a model-invented ``tasks``/``priority``/``label``/``urgent`` key must fail here
rather than be silently dropped.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from interaction.resources import ResourceRequest


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


#: The four §4 workflow steps an UPDATE may ask for. ``AREA_RECON`` is not a
#: workflow step (§4) and is rejected at the schema level.
UpToStep = Literal[
    "THERMAL_RECON",
    "SUPPRESSANT_DROP",
    "GROUND_INSPECTION",
    "GROUND_SUPPRESSION",
]


class NewMissionIntent(_StrictModel):
    """Create the first mission and optionally retain its incident policy."""

    kind: Literal["NEW_MISSION"]
    incident_response_up_to: UpToStep | None = None
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


class UpdateMissionIntent(_StrictModel):
    """Extend one incident's planned response up to a workflow step."""

    kind: Literal["UPDATE_MISSION"]
    target_phrase: str | None = None  # raw referent, e.g. "거기" / "FIRE_SITE_1"
    up_to_step: UpToStep | None = None


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
        "UPDATE_MISSION",
        "QUERY_STATUS",
        "UNSUPPORTED",
    ]
    zone_ref: str | None
    target_phrase: str | None
    up_to_step: UpToStep | None
    incident_response_up_to: UpToStep | None
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
        allowed = {
            "NEW_MISSION": {
                "incident_response_up_to",
                "uav_exact",
                "uav_min",
                "uav_max",
                "ugv_exact",
                "ugv_min",
                "ugv_max",
                "required_agents",
                "excluded_agents",
            },
            "REPORT_INCIDENT": {"zone_ref", "response_up_to"},
            "UPDATE_MISSION": {"target_phrase", "up_to_step"},
            "QUERY_STATUS": {"target_phrase", "about"},
            "UNSUPPORTED": {"note"},
        }[self.kind]
        values = {
            "zone_ref": self.zone_ref,
            "target_phrase": self.target_phrase,
            "up_to_step": self.up_to_step,
            "incident_response_up_to": self.incident_response_up_to,
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
        if self.kind == "NEW_MISSION":
            ResourceRequest.from_flat_slots(values)
        return self

    def to_internal(self) -> IntentEnvelope:
        allowed = {
            "NEW_MISSION": ("incident_response_up_to",),
            "REPORT_INCIDENT": ("zone_ref", "response_up_to"),
            "UPDATE_MISSION": ("target_phrase", "up_to_step"),
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
        if self.kind == "NEW_MISSION":
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
            if any(value is not None for value in resource_values.values()):
                payload["resources"] = ResourceRequestSchema.model_validate(
                    {
                        **resource_values,
                        "required_agents": tuple(resource_values["required_agents"] or ()),
                        "excluded_agents": tuple(resource_values["excluded_agents"] or ()),
                    }
                )
        return IntentEnvelope.model_validate({"intent": payload})


def wire_intent(kind: str, **slots) -> IntentWireEnvelope:
    """Test/demo helper that still crosses the exact live wire boundary."""
    payload = {
        "kind": kind,
        "zone_ref": None,
        "target_phrase": None,
        "up_to_step": None,
        "incident_response_up_to": None,
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
    "UpdateMissionIntent",
    "QueryStatusIntent",
    "UnsupportedIntent",
    "OperatorIntent",
    "IntentEnvelope",
    "IntentWireEnvelope",
    "wire_intent",
]
