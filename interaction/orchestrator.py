"""The planning-session turn loop (RESEARCH_CONTRACT.md §18.3, §18.4, §18.9).

One function owns a turn, so the §18.4 lifecycle is enforced in exactly one
place rather than being re-derived by every caller (a UI included). What it
guarantees, and what the tests pin:

- ``turn_count`` advances exactly once, at the start of the turn.
- ``session.scene`` and ``session.state`` are replaced ONLY by a committed
  ``register_incident`` / ``generate_mission`` / ``apply_patch``. Every other
  outcome — clarification, UNSUPPORTED, QUERY, a rejected patch, NO_CHANGE —
  leaves both objects identical (`is`, not just equal).
- ``allocate`` runs only when the graph actually changed, so a NO_CHANGE or a
  scene-only REPORT never silently reshuffles the plan.
- referents are added only here, only through ``note_referent``, and only when
  the referent resolved AND the turn did not fail.

That last rule is slightly wider than "after a commit": §18.5 adds a referent
for an UPDATE that grounded correctly, and NO_CHANGE is a correctly grounded
turn with nothing left to do. Without it, "거기 진압까지" answered with
NO_CHANGE would drop the referent the operator is about to reuse. A patch the
Validator rejects is a failed UPDATE (§18.5) and adds nothing.

Not here yet: the execute action, live/cached backends and the UI (P8.3).
"""

from dataclasses import dataclass, field
from enum import Enum

from allocation.allocate import AllocationResult, allocate
from interaction.audit import (
    GenerationAudit,
    GroundingAudit,
    PatchAudit,
    PlanAssignmentChanges,
    TurnAudit,
)
from interaction.ground import (
    GroundingOutcome,
    GroundingStatus,
    build_chain_patch,
    resolve_incident,
    resolve_zone,
)
from interaction.interpret import classify
from interaction.scene_mut import register_incident
from interaction.session import MissionSession, ReferentKind, SessionPhase, fresh_session_state
from llm.pipeline import GenerationResult, generate_mission
from validator.hashing import scene_hash
from validator.patch_apply import PatchResult, apply_patch

_WORKFLOW_STEPS = "THERMAL_RECON, SUPPRESSANT_DROP, GROUND_INSPECTION, GROUND_SUPPRESSION"

_UNSUPPORTED_TEMPLATE = (
    "이 세션은 임무 생성·화재 보고·대응 단계 확장·상태 질문만 지원합니다. "
    "요청하신 내용은 지원 범위 밖입니다."
)
_AFTER_EXECUTION_TEMPLATE = (
    "임무가 이미 실행됐습니다. 계획 변경은 새 세션에서 시작해 주세요. "
    "현재 결과 조회는 가능합니다."
)


class TurnOutcome(str, Enum):
    COMMITTED = "COMMITTED"                  # scene or state advanced
    NO_CHANGE = "NO_CHANGE"                  # grounded fine, nothing to do (§18.6)
    ANSWERED = "ANSWERED"                    # read-only QUERY
    CLARIFICATION = "CLARIFICATION"          # grounder asked back (§18.5)
    UNSUPPORTED = "UNSUPPORTED"              # out of scope (§18.2)
    REJECTED = "REJECTED"                    # Validator refused the change
    TURN_ERROR = "TURN_ERROR"                # backend/schema failure, session survives


@dataclass(frozen=True, slots=True)
class TurnResult:
    outcome: TurnOutcome
    audit: TurnAudit
    message: str = ""
    intent_kind: str | None = None
    grounding: GroundingOutcome | None = None
    generation: GenerationResult | None = None
    patch_result: PatchResult | None = None
    plan: AllocationResult | None = None
    error: str | None = None

    @property
    def changed_state(self) -> bool:
        return self.audit.state_changed

    @property
    def changed_scene(self) -> bool:
        return self.audit.scene_changed


@dataclass
class _Turn:
    """Mutable scratch for one turn; frozen into a TurnAudit at the end."""

    session: MissionSession
    utterance: str
    mode: str
    turn_id: str
    pre_scene_hash: str
    pre_graph_hash: str | None
    pre_plan: dict[str, str] | None
    intent_kind: str | None = None
    slots: dict = field(default_factory=dict)
    grounding: GroundingOutcome | None = None
    generation: GenerationResult | None = None
    patch_result: PatchResult | None = None
    referent_noted: str | None = None
    resolved_models: list[str] = field(default_factory=list)
    answer: str | None = None


def _mode_of(backend) -> str:
    return "mock" if type(backend).__name__ == "MockBackend" else "live"


def _graph_hash_of(session: MissionSession) -> str | None:
    if session.state is None:
        return None
    from validator.hashing import graph_hash
    from validator.patch import graph_edge_keys, graph_hash_nodes

    graph = session.state.graph
    return graph_hash(graph_hash_nodes(graph), sorted(graph_edge_keys(graph)))


def _grounding_audit(outcome: GroundingOutcome | None) -> GroundingAudit | None:
    if outcome is None:
        return None
    return GroundingAudit(
        status=outcome.status.value,
        entity_kind=outcome.entity_kind.value if outcome.entity_kind else None,
        entity_id=outcome.entity_id,
        clarification=outcome.clarification,
        candidates=list(outcome.candidates),
    )


def _patch_audit(result: PatchResult | None) -> PatchAudit | None:
    if result is None:
        return None
    return PatchAudit(
        accepted=result.accepted,
        error_codes=[c.value for c in result.error_codes],
        added_tasks=list(result.added_tasks),
        added_edges=[list(e) for e in result.added_edges],
        directly_released_tasks=list(result.directly_released_tasks),
        status_changes=[list(sc) for sc in result.status_changes],
    )


def _generation_audit(gen: GenerationResult | None) -> GenerationAudit | None:
    if gen is None:
        return None
    return GenerationAudit(
        approved=gen.approved,
        failure_category=gen.failure_category,
        graph_hash=gen.validation.graph_hash if gen.validation else "",
        error_codes=[c.value for c in gen.validation.error_codes] if gen.validation else [],
        repaired=gen.repaired,
    )


def _finish(
    turn: _Turn, outcome: TurnOutcome, message: str, error: str | None = None
) -> TurnResult:
    session = turn.session
    post_plan = session.plan.assignments if session.plan else None
    audit = TurnAudit(
        session_id=session.session_id,
        turn_id=turn.turn_id,
        utterance=turn.utterance,
        mode=turn.mode,
        outcome=outcome.value,
        intent_kind=turn.intent_kind,
        extracted_slots=dict(turn.slots),
        grounding=_grounding_audit(turn.grounding),
        pre_scene_hash=turn.pre_scene_hash,
        post_scene_hash=scene_hash(session.scene),
        pre_graph_hash=turn.pre_graph_hash,
        post_graph_hash=_graph_hash_of(session),
        pre_state_hash=turn.patch_result.pre_state_hash if turn.patch_result else None,
        patch_hash=turn.patch_result.patch_hash if turn.patch_result else None,
        patch=_patch_audit(turn.patch_result),
        generation=_generation_audit(turn.generation),
        plan_assignment_changes=PlanAssignmentChanges.between(turn.pre_plan, post_plan),
        scene_changed=scene_hash(session.scene) != turn.pre_scene_hash,
        state_changed=_graph_hash_of(session) != turn.pre_graph_hash,
        referent_noted=turn.referent_noted,
        resolved_models=list(turn.resolved_models),
        answer=turn.answer,
    )
    session.turn_log.append(audit)
    return TurnResult(
        outcome=outcome,
        audit=audit,
        message=message,
        intent_kind=turn.intent_kind,
        grounding=turn.grounding,
        generation=turn.generation,
        patch_result=turn.patch_result,
        plan=session.plan,
        error=error,
    )


def _clarify(turn: _Turn, outcome: GroundingOutcome) -> TurnResult:
    turn.grounding = outcome
    return _finish(turn, TurnOutcome.CLARIFICATION, outcome.clarification or "")


def _note(turn: _Turn, kind: ReferentKind, entity_id: str) -> None:
    turn.session.note_referent(kind, entity_id)
    turn.referent_noted = entity_id


def _replan(session: MissionSession) -> None:
    """Plan-time re-analysis of the committed graph (§18, `allocate` usage rule).

    Called only when the graph actually changed. This is a fresh plan-time
    analysis, not a reallocation of anything in flight.
    """
    session.plan = allocate(session.state, session.scene)


# -- dialogue acts -----------------------------------------------------


def _do_new_mission(turn: _Turn, backend) -> TurnResult:
    session = turn.session
    if session.state is not None:
        return _clarify(
            turn,
            GroundingOutcome(
                GroundingStatus.CLARIFICATION_REQUIRED,
                clarification=(
                    "이미 활성 임무가 있습니다. 기존 임무를 수정하려면 어느 화재 지점을 "
                    "어느 단계까지 처리할지 말씀해 주세요."
                ),
            ),
        )

    gen = generate_mission(turn.utterance, session.scene, backend)
    turn.generation = gen
    if not gen.approved or gen.graph is None:
        return _finish(
            turn,
            TurnOutcome.REJECTED,
            f"임무 생성이 거부됐습니다 ({gen.failure_category}).",
        )

    session.state = fresh_session_state(gen.graph, session.scene)
    _replan(session)
    return _finish(
        turn,
        TurnOutcome.COMMITTED,
        f"임무를 생성했습니다: task {len(session.state.graph)}개, "
        f"edge {len(session.state.graph.edges)}개.",
    )


def _do_report_incident(turn: _Turn) -> TurnResult:
    session = turn.session
    zone = resolve_zone(session.scene, turn.slots.get("zone_ref"))
    turn.grounding = zone
    if not zone.resolved:
        return _clarify(turn, zone)

    session.scene, incident_id = register_incident(session.scene, zone.entity_id)
    _note(turn, ReferentKind.INCIDENT, incident_id)
    return _finish(
        turn,
        TurnOutcome.COMMITTED,
        f"{zone.entity_id}에 화재 지점 {incident_id}을(를) 등록했습니다.",
    )


def _do_update_mission(turn: _Turn) -> TurnResult:
    session = turn.session
    if session.state is None:
        return _clarify(
            turn,
            GroundingOutcome(
                GroundingStatus.CLARIFICATION_REQUIRED,
                clarification="활성 임무가 없습니다. 먼저 임무를 생성해 주세요.",
            ),
        )

    incident = resolve_incident(session, turn.slots.get("target_phrase"))
    turn.grounding = incident
    if not incident.resolved:
        return _clarify(turn, incident)

    up_to_step = turn.slots.get("up_to_step")
    if up_to_step is None:
        return _clarify(
            turn,
            GroundingOutcome(
                GroundingStatus.CLARIFICATION_REQUIRED,
                clarification=(
                    f"{incident.entity_id}을(를) 어느 단계까지 처리할까요? ({_WORKFLOW_STEPS})"
                ),
            ),
        )

    plan = build_chain_patch(session.state.graph, incident.entity_id, up_to_step)
    if plan.no_change:
        # Grounded correctly, nothing to commit: keep the referent, skip allocate.
        _note(turn, ReferentKind.INCIDENT, incident.entity_id)
        return _finish(turn, TurnOutcome.NO_CHANGE, plan.note)

    committed, result = apply_patch(session.state, plan.patch, session.scene)
    turn.patch_result = result
    if not result.accepted:
        codes = ", ".join(c.value for c in result.error_codes)
        return _finish(turn, TurnOutcome.REJECTED, f"변경이 거부됐습니다 ({codes}).")

    session.state = committed
    _replan(session)
    _note(turn, ReferentKind.INCIDENT, incident.entity_id)
    return _finish(turn, TurnOutcome.COMMITTED, plan.note)


def _describe_status(session: MissionSession, incident_id: str | None, about: str) -> str:
    if session.state is None:
        return "활성 임무가 없습니다."
    graph = session.state.graph
    assignments = session.plan.assignments if session.plan else {}

    tasks = [t for t in graph.tasks if incident_id is None or t.target == incident_id]
    if not tasks:
        return f"{incident_id}에 대한 task가 계획에 없습니다."
    if about == "incidents":
        return "등록된 화재 지점: " + ", ".join(session.known_incident_ids)

    lines = [
        f"  {t.task_id} -> {assignments.get(t.task_id, '미할당')} ({t.status.value})"
        for t in sorted(tasks, key=lambda t: t.task_id)
    ]
    head = f"{incident_id} 대응" if incident_id else "현재 계획"
    return f"{head} ({len(tasks)} task):\n" + "\n".join(lines)


def _do_query_status(turn: _Turn) -> TurnResult:
    session = turn.session
    target_phrase = turn.slots.get("target_phrase")
    incident_id = None
    if target_phrase is not None:
        incident = resolve_incident(session, target_phrase)
        turn.grounding = incident
        if not incident.resolved:
            return _clarify(turn, incident)
        incident_id = incident.entity_id

    turn.answer = _describe_status(session, incident_id, turn.slots.get("about", "mission"))
    if incident_id is not None:
        _note(turn, ReferentKind.INCIDENT, incident_id)
    return _finish(turn, TurnOutcome.ANSWERED, turn.answer)


# -- the turn ----------------------------------------------------------


_PLANNING_ONLY = {"NEW_MISSION", "REPORT_INCIDENT", "UPDATE_MISSION"}


def handle_turn(session: MissionSession, utterance: str, backend) -> TurnResult:
    """Run one operator turn. Never raises for a backend or schema failure —
    the session survives and the turn is recorded as ``TURN_ERROR``."""
    session.turn_count += 1
    before = len(getattr(backend, "resolved_models", ()))
    turn = _Turn(
        session=session,
        utterance=utterance,
        mode=_mode_of(backend),
        turn_id=f"t{session.turn_count}",
        pre_scene_hash=scene_hash(session.scene),
        pre_graph_hash=_graph_hash_of(session),
        pre_plan=dict(session.plan.assignments) if session.plan else None,
    )

    try:
        intent = classify(session, utterance, backend)
    except Exception as exc:  # noqa: BLE001 - one bad turn must not kill the session
        turn.resolved_models = list(getattr(backend, "resolved_models", ())[before:])
        return _finish(
            turn,
            TurnOutcome.TURN_ERROR,
            "요청을 해석하지 못했습니다. 다시 말씀해 주세요.",
            error=f"{type(exc).__name__}: {exc}",
        )

    turn.resolved_models = list(getattr(backend, "resolved_models", ())[before:])
    turn.intent_kind = intent.kind
    turn.slots = {
        k: v for k, v in intent.model_dump().items() if k != "kind" and v is not None
    }

    if intent.kind in _PLANNING_ONLY and session.phase is not SessionPhase.PLANNING:
        return _finish(turn, TurnOutcome.UNSUPPORTED, _AFTER_EXECUTION_TEMPLATE)

    if intent.kind == "NEW_MISSION":
        return _do_new_mission(turn, backend)
    if intent.kind == "REPORT_INCIDENT":
        return _do_report_incident(turn)
    if intent.kind == "UPDATE_MISSION":
        return _do_update_mission(turn)
    if intent.kind == "QUERY_STATUS":
        return _do_query_status(turn)
    return _finish(turn, TurnOutcome.UNSUPPORTED, _UNSUPPORTED_TEMPLATE)


__all__ = ["TurnOutcome", "TurnResult", "handle_turn"]
