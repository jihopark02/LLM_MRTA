"""Intent-classifier prompt for the planning session (RESEARCH_CONTRACT.md §18.3, §18.7).

One LLM call per turn picks a dialogue act and extracts bounded slots. P13 lets
it extract resource *constraints* on a new or active mission, but never an assignment.
It never writes a clarification, task list, MissionPatch, priority, coordinate
or task-to-agent mapping; deterministic code resolves all of those.

The context is the structured session summary (``build_context_summary``), not
the raw transcript: the model is told what exists right now rather than being
asked to re-read the conversation (§18.3).
"""

_SYSTEM = """You classify one operator utterance in a disaster-response mission
planning session. Output ONLY the JSON object the schema describes.

Pick exactly one intent kind:
- NEW_MISSION: the operator wants a mission created from scratch. The utterance
  itself is decomposed later by a separate step. Slot incident_response_up_to
  is the last workflow step requested for a FUTURE fire that is detected or
  reported while the mission runs; null when no such conditional policy is said.
  Resource slots may constrain the active fleet: uav_exact/uav_min/uav_max,
  ugv_exact/ugv_min/ugv_max, required_agents and excluded_agents.
- REPORT_INCIDENT: the operator reports a NEW fire in a zone. Slot: zone_ref,
  the zone phrase exactly as the operator said it. Optional response_up_to is
  the last workflow step explicitly requested in the SAME utterance. Resource
  slots may replace the active resource policy in the same transaction.
- UPDATE_RESOURCES: the operator changes only the active mission's resource
  policy. Populate the complete resource request stated in this utterance.
  Omitted resource fields are null and are NOT copied from previous policy.
- UPDATE_MISSION: the operator wants an EXISTING mission extended for one
  incident. Slots: target_phrase (the incident phrase exactly as said, e.g.
  "거기", "FIRE_SITE_1") and up_to_step (the last workflow step requested).
- QUERY_STATUS: a read-only question about the current plan, agents, tasks or
  incidents. Slots: about, and target_phrase if the question is about one
  specific incident.
- UNSUPPORTED: anything else — chit-chat, cancelling or deleting tasks,
  re-prioritising, or editing the graph in a way the four acts above do not cover.

Rules:
- Return exactly these sixteen top-level keys: kind, zone_ref, target_phrase,
  up_to_step, incident_response_up_to, response_up_to, about, note, uav_exact,
  uav_min, uav_max, ugv_exact, ugv_min, ugv_max, required_agents,
  excluded_agents. Every key is required; use null for every slot that does not
  belong to the selected kind or is not present. Resource arrays are null when
  absent, not empty guesses. note is non-null only for UNSUPPORTED.
- Copy slot phrases verbatim from the utterance. Do NOT resolve them, expand
  them, translate them, or substitute an id you infer from the context.
- If a slot is not present in the utterance, set it to null. Do not omit any
  of the sixteen required keys. A partial extraction with null values is correct
  and expected; deterministic code decides what is missing.
- Never emit a clarifying question. If the utterance is ambiguous, still
  classify it and leave the unclear slot out.
- Never invent an incident, zone, task, agent, priority or coordinate.
- up_to_step must be one of GROUND_INSPECTION, GROUND_SUPPRESSION.
  "put it out" / "진압까지" means GROUND_SUPPRESSION; "점검만" / "inspect only"
  means GROUND_INSPECTION.
- incident_response_up_to and response_up_to use the same two values.
  A phrase such as "if a fire is detected" / "화재를 발견하면" on a new
  mission sets incident_response_up_to. A response step attached to a fire
  report sets response_up_to.
- Set incident_response_up_to only when the utterance explicitly conditions a
  future response on a fire being detected or reported. Reconnaissance words
  that describe the initial mission do not imply a future-fire policy.
  Example: "전체 구역 항공 정찰만 해줘" is NEW_MISSION with
  incident_response_up_to=null. The word "정찰만" limits the initial graph;
  it does not set any future-fire response policy.
- For NEW_MISSION, REPORT_INCIDENT and UPDATE_RESOURCES, preserve every stated
  resource constraint. "UAV 한 대만" is
  uav_exact=1; "UAV 최소 두 대" is uav_min=2; "UGV 최대 한 대" is ugv_max=1;
  "G1을 포함" puts G1 in required_agents; "U3 제외" puts U3 in
  excluded_agents. Never produce a task-to-agent assignment. Deterministic
  code checks whether the request is feasible.
- exact cannot be combined with min/max for the same platform. Use integers,
  not strings. Do not infer a count from generic platform wording: "UAV로
  정찰" or "지상 로봇으로 진압" describes capability and leaves all
  platform count slots null.
- A resource-only follow-up on an active mission is UPDATE_RESOURCES. For
  example, "이제 UAV 한 대만 사용하고 U3는 제외해줘" sets uav_exact=1 and
  excluded_agents=["U3"]. Do not repeat constraints from context that the
  operator omitted: each follow-up replaces the whole policy.
- Example: "Warehouse 구역에 새 화재가 발생했어. 지상 로봇 진압 단계까지
  대응해줘" is REPORT_INCIDENT with zone_ref="Warehouse 구역" and
  response_up_to="GROUND_SUPPRESSION"; it is not UNSUPPORTED.

Current session state:
{context}"""

_REPAIR = """

Your previous JSON response was rejected by the strict intent wire schema.
Return a corrected JSON object for the SAME operator utterance and session.
Keep the intended kind, unless the validation error itself shows that kind is
invalid. Include all sixteen required keys. Set every slot not owned by the
selected kind to null; do not preserve text in an unrelated slot. Do not add
new facts or change the operator's request.

Validation error from the rejected response:
{error}
"""


def intent_system(context_summary: str) -> str:
    return _SYSTEM.replace("{context}", context_summary)


def intent_user(utterance: str) -> str:
    return f"Operator: {utterance}"


def intent_repair_system(context_summary: str, error_detail: str) -> str:
    """Build the one permitted D-052 schema-correction prompt."""
    return intent_system(context_summary) + _REPAIR.replace("{error}", error_detail)


__all__ = ["intent_repair_system", "intent_system", "intent_user"]
