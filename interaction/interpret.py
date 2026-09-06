"""The single LLM call of a planning turn (RESEARCH_CONTRACT.md §18.3, §18.7).

Thin on purpose: build the prompt from the structured session, ask the backend
for an ``IntentEnvelope``, hand back the intent. Everything that decides what
the intent *means* is deterministic and lives in ``interaction/ground.py``.

The context is flattened into the user payload rather than sent as a message
history, so the existing ``LLMBackend`` protocol is unchanged (§18.3 — the
model sees a deterministic summary, never the raw transcript).
"""

from interaction.prompts import intent_system, intent_user
from interaction.schemas import IntentEnvelope, OperatorIntent
from interaction.session import MissionSession


def classify(session: MissionSession, utterance: str, backend) -> OperatorIntent:
    """Classify one utterance. A schema-invalid response raises
    ``pydantic.ValidationError`` — the orchestrator turns it into a recorded
    turn error rather than letting it abort the session."""
    envelope = backend.complete(
        intent_system(session.context_for_llm()),
        intent_user(utterance),
        IntentEnvelope,
    )
    return envelope.intent


__all__ = ["classify"]
