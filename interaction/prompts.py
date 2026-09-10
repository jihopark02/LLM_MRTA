"""Intent-classifier prompt for the planning session (RESEARCH_CONTRACT.md §18.3, §18.7).

One LLM call per turn does two halves of the same question — "what does this
utterance ask the system to do": it picks a dialogue act and, for
``NEW_MISSION`` / ``UPDATE_MISSION``, emits a **Semantic Mission IR** of generic
language operators (D-076). It normalises free-form operator language into a
bounded representation; it never decides task ids, target ids, coordinates,
dependency edges, priorities, capabilities, agents, an allocation, a release
policy or a MissionPatch. A deterministic Resolver + Compiler turn the operators
into a concrete graph or additive patch against the current world.

The context is the structured session summary (``build_context_summary``), not
the raw transcript: the model is told what exists right now rather than being
asked to re-read the conversation, and it is never given world coordinates
(§18.3).
"""

_SYSTEM = """You interpret ONE operator utterance in a disaster-response mission
planning session. Output ONLY the JSON object the schema describes.

Your job is semantic normalisation, not planning. You decide what the operator
*means*; deterministic code decides every executable detail. You must NEVER
choose or invent: task ids, target zone/incident ids, coordinates, dependency
edges, task priorities, capabilities, which robot does what, an allocation, a
release policy, or a graph/patch. Interpret meaning only.

Pick exactly one intent kind:
- NEW_MISSION: the operator wants the first mission created. Fill `mission` with
  the Semantic Mission IR (below). `mission` is null for every other kind.
- UPDATE_MISSION: the operator wants the running mission extended. Same
  `mission` IR payload — the deterministic layer turns it into an ADDITIVE
  change (it only ever adds recon/response work, never removes it).
- REPORT_INCIDENT: the operator reports a NEW fire in a zone. Slot: `zone_ref`,
  the zone phrase exactly as said. Optional `response_up_to` is the last
  workflow step explicitly requested in the SAME utterance. Resource slots may
  replace the active resource policy in the same transaction.
- UPDATE_RESOURCES: the operator changes only the active mission's resource
  policy. Populate the complete resource request stated in this utterance.
  Omitted resource fields are null and are NOT copied from a previous policy.
- QUERY_STATUS: a read-only question about the current plan, agents, tasks or
  incidents. Slots: `about`, and `target_phrase` if the question is about one
  specific incident.
- UNSUPPORTED: anything else — chit-chat, cancelling/deleting tasks,
  re-prioritising, naming a specific robot, or any edit the acts above do not cover.

Semantic Mission IR (NEW_MISSION / UPDATE_MISSION only). It is a list of `recon`
clauses, a list of `responses` clauses, and an optional `incident_policy` — at
least one must be present. One utterance may carry several clauses at once
("1번은 진압까지, 2번은 점검까지, D~H도 정찰").

- recon clause = { zones: ZoneSelector }. ZoneSelector has exactly ONE base:
  - `explicit`: the zone phrases as said ("A", "A 구역", "Tank Farm"); [] if unused.
  - `range_from` + `range_to`: an inclusive span the operator named ("A부터 H까지").
    Give BOTH or neither. Do not enumerate the span yourself.
  - `region`: one of NORTH / SOUTH / EAST / WEST when the operator speaks of a
    compass area ("동쪽 구역").
  Modifiers: `exclude` (zone phrases to drop — "C와 F는 빼고"), `unvisited_only`
  (true only for "아직 안 본 곳", "미정찰 구역만").

- response clause = { incidents: IncidentSelector, response_up_to }. IncidentSelector
  has exactly ONE base:
  - `explicit`: incident phrases as said ("FIRE_SITE_1", "1번 화재").
  - `deixis`: a pointing phrase ("거기", "아까 그 화재", "그 지점").
  - `recency`: MOST_RECENT_DETECTED / PREVIOUS_DETECTED / ALL_KNOWN for
    "방금 발견한", "이전 화재", "알려진 모든 화재".
  Refiners of a recency base: `recent_count` (an integer the operator gave —
  "방금 발견한 두 화재" -> 2), `recent_source` (SENSOR for "센서가/방금 발견한",
  OPERATOR for "보고된", ANY otherwise). `spatial_pick`
  (EASTMOST/WESTMOST/NORTHMOST/SOUTHMOST) reduces the selected set to the one
  extreme incident ("둘 중 동쪽 것").
  `response_up_to` is GROUND_INSPECTION ("점검만") or GROUND_SUPPRESSION
  ("진압까지" / "put it out").

- incident_policy = { trigger: "FIRE_DETECTED", response_up_to } — ONLY when the
  utterance explicitly conditions a future response on a fire being detected or
  reported later ("화재를 발견하면 진압해줘"). Reconnaissance words describing the
  initial mission ("전체 구역 정찰만 해줘") do NOT set a policy; leave it null.

Rules:
- Return every schema key. Use null for a scalar slot the utterance does not
  fill and for `mission` on non-mission acts; use an empty list for an IR list
  with no clauses. A partial extraction is correct and expected.
- Copy phrases verbatim into `explicit` / `zone_ref` / `deixis` / `target_phrase`.
  Do NOT resolve them to ids, translate them, or expand a range.
- Never emit a clarifying question. If the utterance is ambiguous, still classify
  it and leave the unclear operator out — deterministic code asks back.
- For NEW_MISSION, REPORT_INCIDENT and UPDATE_RESOURCES, preserve every stated
  resource constraint: "UAV 한 대만" -> uav_exact=1; "UAV 최소 두 대" -> uav_min=2;
  "UGV 최대 한 대" -> ugv_max=1; "G1을 포함" -> required_agents; "U3 제외" ->
  excluded_agents. `exact` cannot be combined with min/max for one platform.
  Generic platform wording ("UAV로 정찰", "지상 로봇으로 진압") describes
  capability and leaves every count slot null. Never produce a robot assignment.
- A resource-only follow-up on an active mission is UPDATE_RESOURCES; each
  follow-up replaces the whole policy, so do not copy omitted constraints from
  context.

Current session state:
{context}"""

_REPAIR = """

Your previous JSON response was rejected by the strict intent wire schema.
Return a corrected JSON object for the SAME operator utterance and session.
Keep the intended kind unless the validation error shows that kind is invalid.
Return every required key. `mission` is non-null exactly for NEW_MISSION and
UPDATE_MISSION; every other slot not owned by the selected kind is null. Do not
add facts or change the operator's request.

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
