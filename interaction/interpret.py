"""The single LLM call of a planning turn (RESEARCH_CONTRACT.md §18.3, §18.7).

Thin on purpose: build the prompt from the structured session, ask the backend
for an ``IntentEnvelope``, hand back the intent. Everything that decides what
the intent *means* is deterministic and lives in ``interaction/ground.py``.

The context is flattened into the user payload rather than sent as a message
history, so the existing ``LLMBackend`` protocol is unchanged (§18.3 — the
model sees a deterministic summary, never the raw transcript).
"""

from dataclasses import dataclass

from pydantic import ValidationError

from interaction.prompts import intent_repair_system, intent_system, intent_user
from interaction.schemas import IntentWireEnvelope, OperatorIntent
from interaction.session import MissionSession


@dataclass(slots=True)
class IntentRepairTrace:
    """Per-turn transport trace; frozen into ``TurnAudit`` by the caller."""

    attempted: bool = False
    recovered: bool = False


def classify(
    session: MissionSession,
    utterance: str,
    backend,
    *,
    repair_trace: IntentRepairTrace | None = None,
) -> OperatorIntent:
    """Classify one utterance with the bounded D-052 wire repair.

    Live/cached mode gets one correction attempt after a schema-invalid first
    response.  A second validation failure (and every mock validation failure)
    reaches the orchestrator, which records it without aborting the session.
    """
    trace = repair_trace if repair_trace is not None else IntentRepairTrace()
    context = session.context_for_llm()
    user = intent_user(utterance)
    try:
        wire = backend.complete(intent_system(context), user, IntentWireEnvelope)
    except ValidationError as error:
        # D-052: this is a bounded retry, not schema laundering.  The repaired
        # response must pass the exact same strict model.  Mock intentionally
        # stays one-shot so a broken published script cannot be hidden.
        if getattr(backend, "mode", None) not in {"live", "cached"}:
            raise
        trace.attempted = True
        wire = backend.complete(
            intent_repair_system(context, str(error)),
            user,
            IntentWireEnvelope,
        )
        trace.recovered = True
    return wire.to_internal().intent


__all__ = ["IntentRepairTrace", "classify"]
