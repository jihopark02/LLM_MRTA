"""Operator intent schemas for the planning session (RESEARCH_CONTRACT.md §18).

The interaction LLM does exactly two things (§18.7): classify the utterance into
one of the five supported dialogue acts (§18.2) and extract slots. It never
emits a clarification, a MissionPatch, a task list, an agent, a priority or a
coordinate. For ``NEW_MISSION`` the task/edge generation is the existing RQ1
``llm.pipeline.generate_mission`` on the raw utterance (§12) — that is why
``NewMissionIntent`` carries no slots at all (D-027).

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
    """Create the first mission. No slots — the raw utterance goes to
    ``generate_mission`` (D-027); the classifier must not decompose it."""

    kind: Literal["NEW_MISSION"]


class ReportIncidentIntent(_StrictModel):
    """The operator reports a new incident — the only NL route by which an
    incident enters the system (§18.1). No ``label`` (ids are generated
    deterministically) and no urgency slot (priority is fixed, §18.10)."""

    kind: Literal["REPORT_INCIDENT"]
    zone_ref: str | None = None  # raw phrase; grounder matches zone_id + aliases


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
    about: Literal["agents", "tasks", "incidents", "mission"] | None
    note: str | None

    @model_validator(mode="after")
    def _kind_owns_non_null_slots(self):
        allowed = {
            "NEW_MISSION": set(),
            "REPORT_INCIDENT": {"zone_ref"},
            "UPDATE_MISSION": {"target_phrase", "up_to_step"},
            "QUERY_STATUS": {"target_phrase", "about"},
            "UNSUPPORTED": {"note"},
        }[self.kind]
        values = {
            "zone_ref": self.zone_ref,
            "target_phrase": self.target_phrase,
            "up_to_step": self.up_to_step,
            "about": self.about,
            "note": self.note,
        }
        unexpected = sorted(
            key for key, value in values.items() if value is not None and key not in allowed
        )
        if unexpected:
            raise ValueError(f"{self.kind} cannot populate slots: {', '.join(unexpected)}")
        return self

    def to_internal(self) -> IntentEnvelope:
        allowed = {
            "NEW_MISSION": (),
            "REPORT_INCIDENT": ("zone_ref",),
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
        return IntentEnvelope.model_validate({"intent": payload})


def wire_intent(kind: str, **slots) -> IntentWireEnvelope:
    """Test/demo helper that still crosses the exact live wire boundary."""
    payload = {
        "kind": kind,
        "zone_ref": None,
        "target_phrase": None,
        "up_to_step": None,
        "about": None,
        "note": None,
    }
    payload.update(slots)
    return IntentWireEnvelope.model_validate(payload)


__all__ = [
    "UpToStep",
    "NewMissionIntent",
    "ReportIncidentIntent",
    "UpdateMissionIntent",
    "QueryStatusIntent",
    "UnsupportedIntent",
    "OperatorIntent",
    "IntentEnvelope",
    "IntentWireEnvelope",
    "wire_intent",
]
