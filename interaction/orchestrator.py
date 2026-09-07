"""The planning-session turn loop (RESEARCH_CONTRACT.md §18.3, §18.4, §18.9).

One function owns a turn, so the §18.4 lifecycle is enforced in exactly one
place rather than being re-derived by every caller (a UI included). What it
guarantees, and what the tests pin:

- ``turn_count`` advances exactly once, at the start of the turn.
- **the whole turn** is exception-isolated, not just the intent call: a backend
  that dies inside ``generate_mission``'s Step1/Step2/repair is a recorded
  ``TURN_ERROR`` too (D-029). A model output that merely fails the *schema* is
  a different thing and keeps P5's meaning — an explicit ``REJECTED`` with a
  ``GenerationAudit``, not an error.
- state and plan move together: the candidate state AND its plan are built in
  locals first, so a failing ``allocate`` cannot leave a half-committed graph
  with a stale plan (D-029).
- ``session.scene`` and ``session.state`` are replaced ONLY by a committed
  ``register_incident`` / ``generate_mission`` / ``apply_patch``. Every other
  outcome — clarification, UNSUPPORTED, QUERY, a rejected patch, NO_CHANGE —
  leaves both objects identical (`is`, not just equal).
- ``allocate`` runs only when the graph actually changed, so a NO_CHANGE or a
  scene-only REPORT never silently reshuffles the plan.
- referents are added only here, only through ``note_referent``, and only when
  the referent resolved AND the turn did not fail. A ``QUERY_STATUS`` resolved
  from a deixis is the exception: it answers but does not refresh the window,
  or repeating "거기 상태" would extend a referent forever (§18.5, D-029).

That last rule is slightly wider than "after a commit": §18.5 adds a referent
for an UPDATE that grounded correctly, and NO_CHANGE is a correctly grounded
turn with nothing left to do. Without it, "거기 진압까지" answered with
NO_CHANGE would drop the referent the operator is about to reuse. A patch the
Validator rejects is a failed UPDATE (§18.5) and adds nothing.

P8.3's Streamlit UI is only a caller of this module. Deterministic execution
and exact live-response caching remain separate in ``interaction.execute`` and
``llm.cache`` so neither concern changes turn semantics.
"""

from dataclasses import dataclass, field
from enum import Enum

from allocation.allocate import AllocationResult, allocate
from allocation.online import (
    ONLINE_POLICY_VERSION,
    OnlinePatchApplication,
    ReleasePolicy,
    apply_online_patch,
)
from core.enums import TaskStatus
from interaction.audit import (
    GenerationAudit,
    GroundingAudit,
    IncidentActionAudit,
    OnlineReallocationAudit,
    PatchAudit,
    PlanAssignmentChanges,
    RuntimeAssignmentChanges,
    TurnAudit,
)
from interaction.directive import MissionDirective
from interaction.ground import (
    ClarificationReason,
    GroundingOutcome,
    GroundingStatus,
    ResolutionVia,
    build_chain_patch,
    resolve_incident,
    resolve_zone,
)
from interaction.incident_response import (
    IncidentSource,
    PolicyOrigin,
    prepare_incident_transaction,
)
from interaction.interpret import classify
from interaction.mode import mode_of_backend, require_mode
from interaction.session import (
    MissionSession,
    PendingClarification,
    ReferentKind,
    SessionPhase,
    fresh_session_state,
)
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
    CLARIFICATION_CANCELLED = "CLARIFICATION_CANCELLED"


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
    backend: object | None
    models_before: int
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
    answer: str | None = None
    input_kind: str = "NATURAL_LANGUAGE"
    resumed_from_turn_id: str | None = None
    selected_entity_id: str | None = None
    online_reallocation: OnlineReallocationAudit | None = None
    incident_action: IncidentActionAudit | None = None

    def resolved_models(self) -> list[str]:
        """Every backend call this turn made — intent classification plus any
        Step1/Step2/repair calls generate_mission triggered (§14, D-029)."""
        return list(getattr(self.backend, "resolved_models", ())[self.models_before :])


def _mode_of(backend) -> str:
    """Response provenance for the audit (§18.9).

    Read from the backend rather than inferred from its class name: a
    ``MockBackend`` subclass or a wrapper would otherwise be logged as live,
    and the contract forbids presenting cached or mocked answers as live. A
    backend that declares nothing is a wiring bug, so it fails immediately
    instead of silently defaulting to "live" — that is a misconfiguration, not
    a turn failure, and must not be swallowed as one.
    """
    return mode_of_backend(backend)


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
        via=outcome.via.value if outcome.via else None,
        clarification=outcome.clarification,
        candidates=list(outcome.candidates),
        reason=outcome.reason.value if outcome.reason else None,
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
    turn: _Turn,
    outcome: TurnOutcome,
    message: str,
    exc: BaseException | None = None,
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
        online_reallocation=turn.online_reallocation,
        incident_action=turn.incident_action,
        scene_changed=scene_hash(session.scene) != turn.pre_scene_hash,
        state_changed=_graph_hash_of(session) != turn.pre_graph_hash,
        referent_noted=turn.referent_noted,
        resolved_models=turn.resolved_models(),
        answer=turn.answer,
        error_type=type(exc).__name__ if exc is not None else None,
        error_detail=str(exc) if exc is not None else None,
        input_kind=turn.input_kind,
        resumed_from_turn_id=turn.resumed_from_turn_id,
        selected_entity_id=turn.selected_entity_id,
    )
    session.append_event(audit)
    return TurnResult(
        outcome=outcome,
        audit=audit,
        message=message,
        intent_kind=turn.intent_kind,
        grounding=turn.grounding,
        generation=turn.generation,
        patch_result=turn.patch_result,
        plan=session.plan,
        error=f"{type(exc).__name__}: {exc}" if exc is not None else None,
    )


def _clarify(turn: _Turn, outcome: GroundingOutcome) -> TurnResult:
    turn.grounding = outcome
    _store_pending_if_resumable(turn, outcome)
    return _finish(turn, TurnOutcome.CLARIFICATION, outcome.clarification or "")


def _store_pending_if_resumable(turn: _Turn, outcome: GroundingOutcome) -> None:
    """Store only a complete, selectable entity ambiguity (D-032)."""
    if (
        outcome.reason is not ClarificationReason.AMBIGUOUS_ENTITY
        or outcome.entity_kind is None
        or len(outcome.candidates) < 2
    ):
        return

    unresolved_slot: str | None = None
    if turn.intent_kind == "REPORT_INCIDENT":
        unresolved_slot = "zone_ref"
    elif turn.intent_kind == "UPDATE_MISSION" and turn.slots.get("up_to_step") is not None:
        unresolved_slot = "target_phrase"
    elif turn.intent_kind == "QUERY_STATUS" and turn.slots.get("target_phrase") is not None:
        unresolved_slot = "target_phrase"
    if unresolved_slot is None:
        return

    turn.session.pending_clarification = PendingClarification(
        source_turn_id=turn.turn_id,
        intent_kind=turn.intent_kind,
        extracted_slots=dict(turn.slots),
        unresolved_slot=unresolved_slot,
        entity_kind=outcome.entity_kind,
        candidates=tuple(outcome.candidates),
        original_utterance=turn.utterance,
    )


def _note(turn: _Turn, kind: ReferentKind, entity_id: str) -> None:
    turn.session.note_referent(kind, entity_id)
    turn.referent_noted = entity_id


def _plan_for(state, scene) -> AllocationResult:
    """Plan-time re-analysis of a candidate graph (§18, `allocate` usage rule).

    Called only when the graph actually changed, and always on a *candidate*
    before it is committed — so if it raises, the session still holds its old
    state and its matching plan (D-029). This is a fresh plan-time analysis,
    not a reallocation of anything in flight.
    """
    return allocate(state, scene)


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
                reason=ClarificationReason.ACTIVE_MISSION,
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

    # Build state and plan as candidates, then swap both in one step.
    candidate_state = fresh_session_state(gen.graph, session.scene)
    candidate_plan = _plan_for(candidate_state, session.scene)
    candidate_directive = MissionDirective.from_slot(
        turn.slots.get("incident_response_up_to")
    )
    session.state, session.plan, session.directive = (
        candidate_state,
        candidate_plan,
        candidate_directive,
    )
    return _finish(
        turn,
        TurnOutcome.COMMITTED,
        f"임무를 생성했습니다: task {len(session.state.graph)}개, "
        f"edge {len(session.state.graph.edges)}개.",
    )


def _do_report_incident(
    turn: _Turn, resolved_zone: GroundingOutcome | None = None
) -> TurnResult:
    session = turn.session
    zone = resolved_zone or resolve_zone(session.scene, turn.slots.get("zone_ref"))
    turn.grounding = zone
    if not zone.resolved:
        return _clarify(turn, zone)

    explicit_step = turn.slots.get("response_up_to")
    if explicit_step is not None:
        response_up_to = MissionDirective.from_slot(explicit_step).incident_response_up_to
        policy_origin = PolicyOrigin.EXPLICIT
    elif session.directive.incident_response_up_to is not None:
        response_up_to = session.directive.incident_response_up_to
        policy_origin = PolicyOrigin.SESSION_POLICY
    else:
        response_up_to = None
        policy_origin = PolicyOrigin.NONE

    if response_up_to is not None and session.state is None:
        return _clarify(
            turn,
            GroundingOutcome(
                GroundingStatus.CLARIFICATION_REQUIRED,
                clarification="화재 대응 task를 추가하려면 먼저 임무를 생성해 주세요.",
                reason=ClarificationReason.MISSING_MISSION,
            ),
        )

    transaction = prepare_incident_transaction(
        session,
        zone.entity_id,
        response_up_to,
        planner=_plan_for,
        online_applier=apply_online_patch,
    )
    turn.patch_result = transaction.patch_result
    if not transaction.accepted:
        codes = ", ".join(c.value for c in transaction.patch_result.error_codes)
        return _finish(turn, TurnOutcome.REJECTED, f"변경이 거부됐습니다 ({codes}).")

    online_audit = (
        _online_reallocation_audit(transaction.online)
        if transaction.online is not None
        else None
    )
    turn.incident_action = IncidentActionAudit(
        source=IncidentSource.OPERATOR.value,
        zone_id=transaction.zone_id,
        incident_id=transaction.incident_id,
        policy_origin=policy_origin.value,
        response_up_to=(
            transaction.response_up_to.value
            if transaction.response_up_to is not None
            else None
        ),
    )
    turn.online_reallocation = online_audit

    # Every fallible computation has completed. Publish the prepared candidate
    # as one session transition, then record its now-valid scene referent.
    session.scene = transaction.scene
    if transaction.online is not None:
        session.runtime = transaction.runtime
        session.state = transaction.state
    elif response_up_to is not None:
        session.state, session.plan = transaction.state, transaction.plan
    elif session.phase is SessionPhase.EXECUTION_PAUSED:
        # Scene-only reports preserve runtime identity and clock (§18.4).
        session.runtime.scene = transaction.scene
    _note(turn, ReferentKind.INCIDENT, transaction.incident_id)

    response_note = ""
    if response_up_to is not None:
        response_note = f" {response_up_to.value}까지 대응 task를 추가했습니다."
        if transaction.online is not None:
            response_note += (
                f" 미시작 task {len(transaction.online.released_tasks)}개를 "
                "release/rebid했습니다."
            )
    return _finish(
        turn,
        TurnOutcome.COMMITTED,
        f"{zone.entity_id}에 화재 지점 {transaction.incident_id}을(를) 등록했습니다."
        f"{response_note}",
    )


def _do_update_mission(
    turn: _Turn, resolved_incident: GroundingOutcome | None = None
) -> TurnResult:
    session = turn.session
    if session.state is None:
        return _clarify(
            turn,
            GroundingOutcome(
                GroundingStatus.CLARIFICATION_REQUIRED,
                clarification="활성 임무가 없습니다. 먼저 임무를 생성해 주세요.",
                reason=ClarificationReason.MISSING_MISSION,
            ),
        )

    incident = resolved_incident or resolve_incident(
        session, turn.slots.get("target_phrase")
    )
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
                reason=ClarificationReason.MISSING_STEP,
            ),
        )

    plan = build_chain_patch(session.state.graph, incident.entity_id, up_to_step)
    if plan.no_change:
        # Grounded correctly, nothing to commit: keep the referent, skip allocate.
        _note(turn, ReferentKind.INCIDENT, incident.entity_id)
        return _finish(turn, TurnOutcome.NO_CHANGE, plan.note)

    if session.phase is SessionPhase.EXECUTION_PAUSED:
        if session.runtime is None:
            raise ValueError("paused session has no online runtime")
        online = apply_online_patch(
            session.runtime,
            plan.patch,
            session.scene,
            policy=ReleasePolicy.SELECTIVE,
        )
        turn.patch_result = online.patch_result
        if not online.accepted:
            codes = ", ".join(c.value for c in online.patch_result.error_codes)
            return _finish(turn, TurnOutcome.REJECTED, f"변경이 거부됐습니다 ({codes}).")
        # Build every fallible derived value before touching session state.
        # note_referent performs the only remaining session validation; publish
        # the candidate runtime/state together only after it succeeds (§19.4).
        online_audit = _online_reallocation_audit(online)
        _note(turn, ReferentKind.INCIDENT, incident.entity_id)
        turn.online_reallocation = online_audit
        session.runtime = online.executor
        session.state = online.executor.work
        return _finish(
            turn,
            TurnOutcome.COMMITTED,
            f"{plan.note} 미시작 task {len(online.released_tasks)}개를 release/rebid했습니다.",
        )

    committed, patch_result = apply_patch(session.state, plan.patch, session.scene)
    turn.patch_result = patch_result
    if not patch_result.accepted:
        codes = ", ".join(c.value for c in patch_result.error_codes)
        return _finish(turn, TurnOutcome.REJECTED, f"변경이 거부됐습니다 ({codes}).")

    candidate_plan = _plan_for(committed, session.scene)
    session.state, session.plan = committed, candidate_plan
    _note(turn, ReferentKind.INCIDENT, incident.entity_id)
    return _finish(turn, TurnOutcome.COMMITTED, plan.note)


def _online_reallocation_audit(
    result: OnlinePatchApplication,
) -> OnlineReallocationAudit:
    changes = result.assignment_changes
    return OnlineReallocationAudit(
        policy=result.policy.value,
        policy_version=ONLINE_POLICY_VERSION,
        simulation_time=result.executor.now,
        patch_added_tasks=list(result.patch_result.added_tasks),
        directly_affected_tasks=list(result.directly_affected_tasks),
        selectively_released_tasks=list(result.released_tasks),
        preserved_active_assignments=dict(result.preserved_active_assignments),
        before_assignments=dict(result.before_assignments),
        after_assignments=dict(result.after_assignments),
        assignment_changes=RuntimeAssignmentChanges(
            added=dict(changes.added),
            removed=dict(changes.removed),
            changed={task: list(owners) for task, owners in changes.changed.items()},
        ),
        consensus_rounds=list(result.consensus_rounds),
    )


def _describe_status(session: MissionSession, incident_id: str | None, about: str) -> str:
    # Incidents live in the scene, not the mission — answerable before any
    # mission exists (§18.4 allows QUERY at any time).
    if about == "incidents":
        known = session.known_incident_ids
        return "등록된 화재 지점: " + (", ".join(known) if known else "없음")
    if session.state is None:
        return "활성 임무가 없습니다."
    graph = session.state.graph
    paused = session.phase is SessionPhase.EXECUTION_PAUSED
    executed = session.phase in {SessionPhase.EXECUTED, SessionPhase.EXECUTION_FAILED}
    if paused:
        assignments = session.runtime.assignments
    elif executed and session.execution is not None:
        assignments = session.execution.assignments
    else:
        assignments = session.plan.assignments if session.plan else {}

    tasks = [t for t in graph.tasks if incident_id is None or t.target == incident_id]
    if not tasks:
        return f"{incident_id}에 대한 task가 계획에 없습니다."

    completed = {
        task.task_id for task in graph.tasks if task.status is TaskStatus.COMPLETED
    }
    lines = []
    for task in sorted(tasks, key=lambda t: t.task_id):
        status = "COMPLETED" if task.task_id in completed else task.status.value
        lines.append(f"  {task.task_id} -> {assignments.get(task.task_id, '미할당')} ({status})")
    head = f"{incident_id} 대응" if incident_id else "현재 계획"
    if paused:
        head += f" 실행 일시정지, simulation time {session.runtime.now:.1f}"
    elif executed:
        if session.execution is None:
            return "최근 실행이 오류로 종료되어 실행 결과가 없습니다."
        head += (
            f" 실행 결과 {session.execution.termination.value}, "
            f"makespan {session.execution.makespan:.1f}"
        )
    return f"{head} ({len(tasks)} task):\n" + "\n".join(lines)


def _do_query_status(
    turn: _Turn, resolved_incident: GroundingOutcome | None = None
) -> TurnResult:
    session = turn.session
    target_phrase = turn.slots.get("target_phrase")
    incident_id = None
    if target_phrase is not None:
        incident = resolved_incident or resolve_incident(session, target_phrase)
        turn.grounding = incident
        if not incident.resolved:
            return _clarify(turn, incident)
        incident_id = incident.entity_id

    turn.answer = _describe_status(session, incident_id, turn.slots.get("about", "mission"))
    # §18.5 / D-029: only an explicitly named incident is a fresh act of
    # reference. A deictic read must not extend the window that resolved it.
    if incident_id is not None and turn.grounding.via is ResolutionVia.EXPLICIT:
        _note(turn, ReferentKind.INCIDENT, incident_id)
    return _finish(turn, TurnOutcome.ANSWERED, turn.answer)


# -- the turn ----------------------------------------------------------


def _dispatch(turn: _Turn, backend) -> TurnResult:
    session = turn.session
    intent = classify(session, turn.utterance, backend)

    turn.intent_kind = intent.kind
    turn.slots = {
        k: v for k, v in intent.model_dump().items() if k != "kind" and v is not None
    }

    if intent.kind == "NEW_MISSION" and session.phase is not SessionPhase.PLANNING:
        return _finish(turn, TurnOutcome.UNSUPPORTED, _AFTER_EXECUTION_TEMPLATE)
    if (
        intent.kind in {"REPORT_INCIDENT", "UPDATE_MISSION"}
        and session.phase not in {SessionPhase.PLANNING, SessionPhase.EXECUTION_PAUSED}
    ):
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


def handle_turn(session: MissionSession, utterance: str, backend) -> TurnResult:
    """Run one operator turn.

    Never raises for a model or backend *failure*. **The whole turn** is
    isolated, not just the intent call: a
    backend that dies inside ``generate_mission``'s Step1/Step2/repair, or an
    ``allocate`` that blows up, is recorded as ``TURN_ERROR`` and the session
    is left exactly as it was (D-029). A model output that fails the pydantic
    *schema* is a different thing — inside ``generate_mission`` that stays P5's
    explicit ``REJECTED`` with a ``GenerationAudit``.

    A backend that does not declare a valid ``mode`` is the one exception: that
    is a wiring bug and raises, because logging its answers under the wrong
    provenance would be worse than stopping (§18.9).
    """
    mode = _mode_of(backend)  # before the counter: a refused turn must not consume a turn id
    session.turn_count += 1
    turn = _Turn(
        session=session,
        utterance=utterance,
        backend=backend,
        models_before=len(getattr(backend, "resolved_models", ())),
        mode=mode,
        turn_id=f"t{session.turn_count}",
        pre_scene_hash=scene_hash(session.scene),
        pre_graph_hash=_graph_hash_of(session),
        pre_plan=dict(session.plan.assignments) if session.plan else None,
    )
    try:
        if session.pending_clarification is not None:
            pending = session.pending_clarification
            turn.resumed_from_turn_id = pending.source_turn_id
            return _clarify(
                turn,
                GroundingOutcome(
                    GroundingStatus.CLARIFICATION_REQUIRED,
                    entity_kind=pending.entity_kind,
                    clarification="후보를 선택하거나 clarification을 취소해 주세요.",
                    candidates=pending.candidates,
                    reason=ClarificationReason.PENDING_SELECTION,
                ),
            )
        return _dispatch(turn, backend)
    except Exception as exc:  # noqa: BLE001 - one bad turn must not kill the session
        return _finish(
            turn,
            TurnOutcome.TURN_ERROR,
            "요청을 처리하지 못했습니다. 다시 말씀해 주세요.",
            exc=exc,
        )


def _deterministic_turn(
    session: MissionSession,
    *,
    utterance: str,
    mode: str,
    input_kind: str,
    pending: PendingClarification,
    selected_entity_id: str | None = None,
) -> _Turn:
    checked_mode = require_mode(mode)
    session.turn_count += 1
    return _Turn(
        session=session,
        utterance=utterance,
        backend=None,
        models_before=0,
        mode=checked_mode,
        turn_id=f"t{session.turn_count}",
        pre_scene_hash=scene_hash(session.scene),
        pre_graph_hash=_graph_hash_of(session),
        pre_plan=dict(session.plan.assignments) if session.plan else None,
        intent_kind=pending.intent_kind,
        slots=dict(pending.extracted_slots),
        input_kind=input_kind,
        resumed_from_turn_id=pending.source_turn_id,
        selected_entity_id=selected_entity_id,
    )


def _candidate_exists(
    session: MissionSession, pending: PendingClarification, entity_id: str
) -> bool:
    known = (
        session.scene.incidents
        if pending.entity_kind is ReferentKind.INCIDENT
        else session.scene.zones
    )
    return entity_id in pending.candidates and entity_id in known


def select_clarification_candidate(
    session: MissionSession, entity_id: str, *, mode: str
) -> TurnResult:
    """Resume a pending entity ambiguity without another LLM call (§18.13)."""
    pending = session.pending_clarification
    if pending is None:
        raise ValueError("no clarification is pending")
    if not isinstance(entity_id, str):
        raise ValueError("entity_id must be a str")
    turn = _deterministic_turn(
        session,
        utterance=entity_id,
        mode=mode,
        input_kind="CANDIDATE_SELECTION",
        pending=pending,
        selected_entity_id=entity_id,
    )
    if not _candidate_exists(session, pending, entity_id):
        return _clarify(
            turn,
            GroundingOutcome(
                GroundingStatus.CLARIFICATION_REQUIRED,
                entity_kind=pending.entity_kind,
                clarification="제시된 후보 중 하나를 선택해 주세요.",
                candidates=pending.candidates,
                reason=ClarificationReason.INVALID_SELECTION,
            ),
        )

    resolved = GroundingOutcome(
        GroundingStatus.RESOLVED,
        pending.entity_kind,
        entity_id,
        ResolutionVia.EXPLICIT,
    )
    turn.grounding = resolved
    try:
        if pending.intent_kind == "REPORT_INCIDENT":
            result = _do_report_incident(turn, resolved)
        elif pending.intent_kind == "UPDATE_MISSION":
            result = _do_update_mission(turn, resolved)
        else:
            result = _do_query_status(turn, resolved)
    except Exception as exc:  # noqa: BLE001 - same session isolation as a natural turn
        return _finish(
            turn,
            TurnOutcome.TURN_ERROR,
            "선택한 후보를 처리하지 못했습니다. 다시 선택하거나 취소해 주세요.",
            exc=exc,
        )

    if result.outcome in {
        TurnOutcome.COMMITTED,
        TurnOutcome.NO_CHANGE,
        TurnOutcome.ANSWERED,
    }:
        session.pending_clarification = None
    return result


def cancel_clarification(session: MissionSession, *, mode: str) -> TurnResult:
    """Cancel a pending ambiguity without changing mission data (§18.13)."""
    pending = session.pending_clarification
    if pending is None:
        raise ValueError("no clarification is pending")
    turn = _deterministic_turn(
        session,
        utterance="clarification 취소",
        mode=mode,
        input_kind="CLARIFICATION_CANCEL",
        pending=pending,
    )
    result = _finish(
        turn,
        TurnOutcome.CLARIFICATION_CANCELLED,
        "후보 선택을 취소했습니다. 요청을 다시 말씀해 주세요.",
    )
    session.pending_clarification = None
    return result


__all__ = [
    "TurnOutcome",
    "TurnResult",
    "handle_turn",
    "select_clarification_candidate",
    "cancel_clarification",
]
