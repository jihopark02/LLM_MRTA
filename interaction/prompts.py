"""Intent-classifier prompt for the planning session (RESEARCH_CONTRACT.md §18.3, §18.7).

One LLM call per turn, and it does exactly two things: pick one of the five
dialogue acts and extract slots. It never writes a clarification, a task list,
a MissionPatch, an agent, a priority or a coordinate — the schema has no field
for any of those, and the deterministic grounder decides what the slots refer
to (§18.7).

The context is the structured session summary (``build_context_summary``), not
the raw transcript: the model is told what exists right now rather than being
asked to re-read the conversation (§18.3).
"""

_SYSTEM = """You classify one operator utterance in a disaster-response mission
planning session. Output ONLY the JSON object the schema describes.

Pick exactly one intent kind:
- NEW_MISSION: the operator wants a mission created from scratch. No slots —
  the utterance itself is decomposed later by a separate step.
- REPORT_INCIDENT: the operator reports a NEW fire in a zone. Slot: zone_ref,
  the zone phrase exactly as the operator said it.
- UPDATE_MISSION: the operator wants an EXISTING mission extended for one
  incident. Slots: target_phrase (the incident phrase exactly as said, e.g.
  "거기", "FIRE_SITE_1") and up_to_step (the last workflow step requested).
- QUERY_STATUS: a read-only question about the current plan, agents, tasks or
  incidents. Slots: about, and target_phrase if the question is about one
  specific incident.
- UNSUPPORTED: anything else — chit-chat, cancelling or deleting tasks,
  re-prioritising, naming which robot to use, or editing the graph in a way the
  four acts above do not cover.

Rules:
- Copy slot phrases verbatim from the utterance. Do NOT resolve them, expand
  them, translate them, or substitute an id you infer from the context.
- If a slot is not present in the utterance, omit it. A partial extraction is
  correct and expected; something else decides what is missing.
- Never emit a clarifying question. If the utterance is ambiguous, still
  classify it and leave the unclear slot out.
- Never invent an incident, zone, task, agent, priority or coordinate.
- up_to_step must be one of THERMAL_RECON, SUPPRESSANT_DROP,
  GROUND_INSPECTION, GROUND_SUPPRESSION. "put it out" / "진압까지" means
  GROUND_SUPPRESSION; "확인만" / "check it" means THERMAL_RECON.

Current session state:
{context}"""


def intent_system(context_summary: str) -> str:
    return _SYSTEM.replace("{context}", context_summary)


def intent_user(utterance: str) -> str:
    return f"Operator: {utterance}"


__all__ = ["intent_system", "intent_user"]
